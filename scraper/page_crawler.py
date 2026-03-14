import re
import json
from urllib.parse import urljoin, urlparse
from playwright.async_api import BrowserContext
from .models import ScrapedPage, ScrapedProduct
from .browser import random_delay

# Multilingual feature keywords
_FEATURE_KEYWORDS = [
    # German
    'qualität', 'material', 'größe', 'farbe', 'gewicht', 'lieferung', 'garantie',
    'maß', 'eigenschaft', 'vorteil', 'funktion', 'inklusive', 'enthält', 'verarbeitung',
    # English
    'quality', 'material', 'size', 'color', 'colour', 'weight', 'delivery', 'warranty',
    'feature', 'benefit', 'includes', 'function', 'performance', 'compatible',
    # French
    'qualité', 'matériau', 'taille', 'couleur', 'poids', 'livraison', 'garantie',
    'fonctionnalité', 'avantage', 'inclus', 'compatible',
    # Polish
    'jakość', 'materiał', 'rozmiar', 'kolor', 'waga', 'dostawa', 'gwarancja',
    'funkcja', 'zaleta', 'zawiera',
]


async def crawl_product_site(
    context: BrowserContext,
    root_url: str,
    max_pages: int = 30,
    timeout_ms: int = 30_000,
) -> ScrapedProduct:
    visited: set[str] = set()
    queue: list[str] = [root_url]
    pages: list[ScrapedPage] = []
    base_domain = urlparse(root_url).netloc

    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await random_delay(0.5, 1.5)

            scraped = await _extract_page(page, url)
            pages.append(scraped)

            # Collect internal links for BFS
            if len(pages) < max_pages:
                links = await page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => e.href)"
                )
                for link in links:
                    parsed = urlparse(link)
                    if parsed.netloc == base_domain and link not in visited:
                        # Skip obviously irrelevant pages
                        if not _should_skip(link):
                            queue.append(link)
        except Exception:
            pass
        finally:
            await page.close()

    return extract_product_from_pages(pages, root_url)


async def _extract_page(page, url: str) -> ScrapedPage:
    title = await page.title()

    meta_desc = ""
    try:
        meta_desc = await page.get_attribute('meta[name="description"]', "content") or ""
    except Exception:
        pass

    # Extract JSON-LD structured data
    structured: dict = {}
    try:
        scripts = await page.eval_on_selector_all(
            'script[type="application/ld+json"]',
            "els => els.map(e => e.textContent)"
        )
        for s in scripts:
            try:
                data = json.loads(s)
                if isinstance(data, dict):
                    structured.update(data)
            except Exception:
                pass
    except Exception:
        pass

    # Get main text content — increase limit to capture more info per page
    text = ""
    try:
        text = await page.evaluate("""
            () => {
                const remove = ['script', 'style', 'nav', 'footer', 'header', 'iframe', 'noscript'];
                remove.forEach(tag => document.querySelectorAll(tag).forEach(e => e.remove()));
                return document.body ? document.body.innerText : '';
            }
        """)
    except Exception:
        pass

    # Normalize whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()[:8000]

    return ScrapedPage(
        url=url,
        title=title,
        text_content=text,
        meta_description=meta_desc,
        structured_data=structured,
    )


def extract_product_from_pages(pages: list[ScrapedPage], root_url: str) -> ScrapedProduct:
    if not pages:
        return ScrapedProduct(
            name="Unbekanntes Produkt",
            description="Keine Beschreibung verfügbar.",
        )

    main_page = pages[0]

    # Try JSON-LD first
    sd = main_page.structured_data
    name = sd.get("name") or sd.get("headline") or main_page.title or "Unbekanntes Produkt"
    description = sd.get("description") or main_page.meta_description or ""
    price = _extract_price(sd, main_page.text_content)
    category = sd.get("category") or sd.get("breadcrumb", {}).get("name") or None

    # Build a rich description by aggregating text from multiple pages
    # Primary: use structured data / meta description as intro paragraph
    if len(description) < 200 and main_page.text_content:
        # Take the most informative chunk from the main page text
        description = (description + " " + main_page.text_content[:800]).strip()

    # Additional context from up to 5 sub-pages (trim to avoid token bloat)
    extra_context_parts: list[str] = []
    for p in pages[1:6]:
        chunk = p.text_content[:600].strip()
        if len(chunk) > 80:  # skip nearly-empty pages
            extra_context_parts.append(f"[{p.title}]\n{chunk}")

    extra_context = "\n\n".join(extra_context_parts)

    # Extract features from bullet points / short sentences across all pages
    features = _extract_features(pages)

    return ScrapedProduct(
        name=str(name)[:200],
        description=description[:1500],
        price=price,
        category=str(category)[:100] if category else None,
        features=features[:20],
        raw_pages=pages,
        extra_context=extra_context[:3000],
    )


def _extract_price(sd: dict, text: str) -> str | None:
    # From structured data
    offer = sd.get("offers", {})
    if isinstance(offer, list) and offer:
        offer = offer[0]
    if isinstance(offer, dict):
        price = offer.get("price")
        currency = offer.get("priceCurrency", "EUR")
        if price:
            return f"{price} {currency}"

    # From text via regex
    match = re.search(r'(\d{1,4}[.,]\d{2})\s*€', text)
    if match:
        return match.group(0)
    match = re.search(r'€\s*(\d{1,4}[.,]\d{2})', text)
    if match:
        return match.group(0)
    return None


def _extract_features(pages: list[ScrapedPage]) -> list[str]:
    features: list[str] = []
    seen: set[str] = set()
    for page in pages[:8]:  # check more pages now
        text = page.text_content
        lines = text.split('\n') if '\n' in text else text.split('. ')
        for line in lines:
            line = line.strip()
            if 5 < len(line) < 120 and line not in seen:
                if any(kw in line.lower() for kw in _FEATURE_KEYWORDS):
                    features.append(line)
                    seen.add(line)
    return features


def _should_skip(url: str) -> bool:
    skip_patterns = [
        '/login', '/logout', '/cart', '/checkout', '/account',
        '/warenkorb', '/kasse', '/mein-konto', '/datenschutz',
        '/impressum', '/agb', '.pdf', '.jpg', '.png', '.css', '.js',
        'javascript:', 'mailto:', 'tel:',
    ]
    url_lower = url.lower()
    return any(p in url_lower for p in skip_patterns)
