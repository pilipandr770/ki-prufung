import random
import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

_LOCALE_CONFIG = {
    "de": {"locale": "de-DE", "timezone": "Europe/Berlin",    "geo": (52.52, 13.405),  "accept_lang": "de-DE,de;q=0.9,en-US;q=0.8"},
    "en": {"locale": "en-GB", "timezone": "Europe/London",    "geo": (51.51, -0.128),  "accept_lang": "en-GB,en;q=0.9,en-US;q=0.8"},
    "fr": {"locale": "fr-FR", "timezone": "Europe/Paris",     "geo": (48.85, 2.350),   "accept_lang": "fr-FR,fr;q=0.9,en-US;q=0.8"},
    "pl": {"locale": "pl-PL", "timezone": "Europe/Warsaw",   "geo": (52.23, 21.012),  "accept_lang": "pl-PL,pl;q=0.9,en-US;q=0.8"},
}

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [
    {name: 'Chrome PDF Plugin'}, {name: 'Chrome PDF Viewer'}, {name: 'Native Client'}
]});
window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};
Object.defineProperty(navigator, 'permissions', {
    get: () => ({query: () => Promise.resolve({state: 'granted'})})
});
"""


async def launch_stealth_browser(
    headless: bool = True,
    language: str = "de",
) -> tuple[Playwright, Browser, BrowserContext]:
    width = random.randint(1280, 1440)
    height = random.randint(768, 900)

    cfg = _LOCALE_CONFIG.get(language, _LOCALE_CONFIG["de"])
    lat, lon = cfg["geo"]

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": width, "height": height},
        locale=cfg["locale"],
        timezone_id=cfg["timezone"],
        geolocation={"latitude": lat, "longitude": lon},
        permissions=["geolocation"],
        extra_http_headers={
            "Accept-Language": cfg["accept_lang"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        },
    )
    # Add language hint to navigator.languages too
    lang_code = cfg["locale"].split("-")[0]
    await context.add_init_script(STEALTH_JS + f"""
Object.defineProperty(navigator, 'languages', {{get: () => ['{cfg["locale"]}', '{lang_code}', 'en-US', 'en']}});
""")
    return pw, browser, context


async def close_browser(pw: Playwright, browser: Browser) -> None:
    try:
        await browser.close()
        await pw.stop()
    except Exception:
        pass


async def random_delay(min_s: float = 0.5, max_s: float = 2.0) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))
