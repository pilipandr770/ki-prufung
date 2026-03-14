"""
EU / DE Website Compliance Checker.

Crawls a website, locates required legal pages (Impressum, Datenschutz,
AGB, Widerrufsbelehrung), analyses their content with Claude, checks the
cookie-consent banner with Claude Vision, and returns a scored
ComplianceReport.

No forms are filled, no accounts are created — purely read-only.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import anthropic
from playwright.async_api import BrowserContext

from config import settings
from .models import (
    ComplianceReport, PageCheck, CookieBannerCheck,
    LegalIssue, Severity,
)

# ── Legal page registry ───────────────────────────────────────────────────────

LEGAL_PAGES: dict[str, dict] = {
    "Impressum": {
        "link_texts": [
            "impressum", "imprint", "legal notice", "rechtliches", "kontakt / impressum",
        ],
        "url_patterns": ["/impressum", "/imprint", "/legal-notice", "/legal"],
        "law": "§5 TMG / §55 Abs. 2 RStV",
        "required": True,
        "required_elements": [
            "Vollständiger Name + Anschrift des Betreibers",
            "Erreichbarkeit: Telefon ODER E-Mail",
            "Umsatzsteuer-ID / Steuer-Nr. (falls vorhanden)",
            "Handelsregistereintrag (bei GmbH / AG / UG / OHG)",
            "Vertretungsberechtigte Person(en)",
        ],
        "prompt_hint": (
            "Focus on: full legal name, physical street address, working contact "
            "(phone or email), company register number and court. "
            "A P.O. box is NOT sufficient as address."
        ),
    },
    "Datenschutzerklärung": {
        "link_texts": [
            "datenschutz", "datenschutzerklärung", "datenschutzrichtlinie",
            "privacy", "privacy policy", "politique de confidentialité",
            "polityka prywatności",
        ],
        "url_patterns": [
            "/datenschutz", "/privacy", "/privacy-policy",
            "/datenschutzerklarung", "/datenschutzerklaerung",
        ],
        "law": "DSGVO Art. 13 / 14",
        "required": True,
        "required_elements": [
            "Identität und Kontaktdaten des Verantwortlichen",
            "Zwecke und Rechtsgrundlagen der Verarbeitung (Art. 6 DSGVO)",
            "Speicherdauer oder Kriterien",
            "Empfänger oder Kategorien von Empfängern",
            "Betroffenenrechte: Auskunft, Berichtigung, Löschung (Art. 15–22 DSGVO)",
            "Recht auf Beschwerde bei Aufsichtsbehörde",
            "Informationen zu eingesetzten Cookies / Tracking-Diensten",
            "Datenschutzbeauftragter (falls pflichtgemäß bestellt)",
        ],
        "prompt_hint": (
            "Check every Art. 13/14 DSGVO element. Pay particular attention "
            "to: legal basis for each processing purpose, data subject rights "
            "(especially right to deletion / erasure), supervisory authority. "
            "Vague statements like 'we protect your data' are not compliant."
        ),
    },
    "AGB": {
        "link_texts": [
            "agb", "allgemeine geschäftsbedingungen", "allgemeine bedingungen",
            "terms", "terms of service", "terms and conditions", "nutzungsbedingungen",
            "conditions générales",
        ],
        "url_patterns": ["/agb", "/terms", "/nutzungsbedingungen", "/terms-of-service"],
        "law": "BGB §305 ff.",
        "required": False,
        "required_elements": [
            "Vertragsgegenstand und Leistungsbeschreibung",
            "Preise, Zahlungsarten und Fälligkeit",
            "Liefer- / Leistungsbedingungen",
            "Widerrufsrecht / Rücktrittsrecht bei Verbraucherverträgen",
            "Haftungsausschluss / Haftungsbeschränkung",
            "Anwendbares Recht und Gerichtsstand",
        ],
        "prompt_hint": (
            "Distinguish B2C vs B2B. For B2C: widerruf / return right is mandatory. "
            "Look for prohibited clauses (e.g. blanket exclusion of liability for bodily harm)."
        ),
    },
    "Widerrufsbelehrung": {
        "link_texts": [
            "widerruf", "widerrufsbelehrung", "widerrufsrecht",
            "cancellation", "right of withdrawal", "return policy",
        ],
        "url_patterns": ["/widerruf", "/cancellation", "/returns", "/widerrufsbelehrung"],
        "law": "§355 BGB / EU-Verbraucherrechte-RL 2011/83/EU",
        "required": False,
        "required_elements": [
            "14-tägige Widerrufsfrist",
            "Vollständige Rücksendeadresse",
            "Muster-Widerrufsformular oder Mustertext",
            "Rückerstattungsregelung (wann, wie)",
            "Beginn und Ende der Widerrufsfrist präzise beschrieben",
        ],
        "prompt_hint": (
            "Check the exact 14-day rule, start of cooling-off period, "
            "and whether a model withdrawal form is provided per Anlage 2 EGBGB."
        ),
    },
}

# ── Claude helpers ─────────────────────────────────────────────────────────────

_SYSTEM_LEGAL = (
    "Du bist ein erfahrener Rechtsanwalt spezialisiert auf deutsches und "
    "europäisches IT-Recht, DSGVO, TMG und E-Commerce-Recht. "
    "Analysiere Rechtstexte von Websites präzise und praxisnah. "
    "Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt — kein Text außerhalb des JSON."
)


def _parse_json_safe(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}


def _analyze_legal_page(
    page_type: str,
    law: str,
    required_elements: list[str],
    content: str,
    prompt_hint: str,
) -> dict:
    elements_list = "\n".join(f"  - {e}" for e in required_elements)
    prompt = (
        f"Analysiere die folgende '{page_type}'-Seite auf Konformität mit {law}.\n\n"
        f"Pflichtangaben:\n{elements_list}\n\n"
        f"Analyse-Hinweis: {prompt_hint}\n\n"
        f"Seiteninhalt:\n\"\"\"\n{content[:4500]}\n\"\"\"\n\n"
        "Antworte mit diesem JSON (alle Felder müssen vorhanden sein):\n"
        "{\n"
        '  "found_elements": ["Pflichtangabe 1", ...],\n'
        '  "missing_elements": ["Pflichtangabe X fehlt", ...],\n'
        '  "issues": [\n'
        '    {"severity": "critical|warning|ok", "issue": "kurze Beschreibung DE", '
        '"recommendation": "konkreter Verbesserungsvorschlag DE"}\n'
        "  ],\n"
        '  "summary": "2-3 Sätze Gesamtbewertung auf Deutsch",\n'
        '  "compliant": false\n'
        "}"
    )
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=800,
            system=_SYSTEM_LEGAL,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json_safe(resp.content[0].text)
    except Exception as exc:
        return {
            "found_elements": [], "missing_elements": [], "issues": [],
            "summary": f"Analyse fehlgeschlagen: {exc}", "compliant": False,
        }


def _analyze_cookie_banner(screenshot_b64: str) -> dict:
    prompt = (
        "Analysiere diesen Screenshot einer Webseite.\n"
        "Prüfe ob ein Cookie-Consent-Banner oder -Dialog sichtbar ist "
        "(Cookiebot, OneTrust, Borlabs, Usercentrics, eigene Lösungen, etc.).\n\n"
        "Antworte mit diesem JSON:\n"
        "{\n"
        '  "banner_present": false,\n'
        '  "reject_option_visible": false,\n'
        '  "pre_checked_boxes": false,\n'
        '  "issues": [\n'
        '    {"severity": "critical|warning|ok", "issue": "DE Beschreibung", '
        '"recommendation": "DE Empfehlung"}\n'
        "  ],\n"
        '  "summary": "2-3 Satz Bewertung auf Deutsch"\n'
        "}"
    )
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return _parse_json_safe(resp.content[0].text)
    except Exception as exc:
        return {
            "banner_present": False, "reject_option_visible": False,
            "pre_checked_boxes": False,
            "issues": [], "summary": f"Prüfung fehlgeschlagen: {exc}",
        }


# ── Page navigation helpers ──────────────────────────────────────────────────

async def _find_legal_urls(page, base_url: str) -> dict[str, str]:
    """Return {page_type: full_url} for every legal page found in nav / footer."""
    all_links: list[dict] = await page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
            text: (a.textContent || '').trim().toLowerCase().replace(/\\s+/g, ' '),
            href: a.href || ''
        }))
        """
    )

    found: dict[str, str] = {}
    for ptype, cfg in LEGAL_PAGES.items():
        # 1. Search by link text
        for link in all_links:
            if any(kw in link["text"] for kw in cfg["link_texts"]):
                href = link["href"]
                if href.startswith("http"):
                    found[ptype] = href
                    break
                if href.startswith("/"):
                    found[ptype] = urljoin(base_url, href)
                    break
        if ptype in found:
            continue
        # 2. Fallback: URL pattern match
        for link in all_links:
            href_lower = link["href"].lower()
            if any(pat in href_lower for pat in cfg["url_patterns"]):
                href = link["href"]
                found[ptype] = href if href.startswith("http") else urljoin(base_url, href)
                break

    return found


async def _fetch_clean_text(context: BrowserContext, url: str) -> str:
    """Load page and return stripped body text (scripts/styles removed)."""
    pg = await context.new_page()
    try:
        await pg.goto(url, wait_until="domcontentloaded", timeout=25_000)
        text: str = await pg.evaluate(
            """
            () => {
                ['script','style','nav','header','footer'].forEach(tag =>
                    document.querySelectorAll(tag).forEach(el => el.remove())
                );
                return document.body ? document.body.innerText.replace(/\\s+/g, ' ').trim() : '';
            }
            """
        )
        return text[:8000]
    except Exception:
        return ""
    finally:
        await pg.close()


# ── Score ─────────────────────────────────────────────────────────────────────

def _score(page_checks: list[PageCheck], cookie: CookieBannerCheck | None) -> tuple[int, str]:
    pts = 100

    imp = next((c for c in page_checks if c.name == "Impressum"), None)
    if not imp or not imp.found:
        pts -= 30
    else:
        pts -= imp.critical_count * 6 + imp.warning_count * 2

    ds = next((c for c in page_checks if c.name == "Datenschutzerklärung"), None)
    if not ds or not ds.found:
        pts -= 25
    else:
        pts -= ds.critical_count * 5 + ds.warning_count * 2

    if cookie:
        if not cookie.present:
            pts -= 20
        elif not cookie.reject_option:
            pts -= 10
        if cookie.pre_checked_boxes:
            pts -= 8

    pts = max(0, min(100, pts))
    grade = "A" if pts >= 90 else "B" if pts >= 75 else "C" if pts >= 60 else "D" if pts >= 40 else "F"
    return pts, grade


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_compliance_check(
    context: BrowserContext,
    url: str,
    on_progress: Optional[Callable[[str], None]] = None,
) -> ComplianceReport:
    def _log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    # ── 1. Load homepage ─────────────────────────────────────────────────
    _log(f"Lade Startseite: {url}")
    main_page = await context.new_page()
    try:
        await main_page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # Screenshot BEFORE clicking anything (catches cookie banner in first impression)
        _log("Screenshot für Cookie-Banner-Prüfung...")
        screenshot_b64 = base64.b64encode(
            await main_page.screenshot(full_page=False, type="png")
        ).decode()

        _log("Suche Rechtsseiten-Links (Footer / Navigation)...")
        found_urls = await _find_legal_urls(main_page, url)
    finally:
        await main_page.close()

    _log(f"Gefunden: {', '.join(found_urls.keys()) or 'keine Rechtsseiten entdeckt'}")

    # ── 2. Cookie banner ─────────────────────────────────────────────────
    _log("Claude analysiert Cookie-Banner (TTDSG / DSGVO)...")
    cb_data = _analyze_cookie_banner(screenshot_b64)
    cookie_check = CookieBannerCheck(
        present=bool(cb_data.get("banner_present")),
        reject_option=bool(cb_data.get("reject_option_visible")),
        pre_checked_boxes=bool(cb_data.get("pre_checked_boxes")),
        screenshot_b64=screenshot_b64,
        claude_analysis=cb_data.get("summary", ""),
        issues=[
            LegalIssue(
                severity=Severity(i.get("severity", "warning")),
                category="Cookie-Banner",
                issue=i.get("issue", ""),
                recommendation=i.get("recommendation", ""),
            )
            for i in cb_data.get("issues", [])
            if i.get("issue")
        ],
    )

    # ── 3. Analyze each legal page ───────────────────────────────────────
    page_checks: list[PageCheck] = []
    for ptype, cfg in LEGAL_PAGES.items():
        page_url = found_urls.get(ptype, "")
        pc = PageCheck(
            name=ptype,
            law_basis=cfg["law"],
            url=page_url,
            found=bool(page_url),
        )

        if page_url:
            _log(f"Lade {ptype}: {page_url}")
            content = await _fetch_clean_text(context, page_url)
            pc.content_excerpt = content[:500]

            _log(f"Claude analysiert {ptype} ({cfg['law']})...")
            result = _analyze_legal_page(
                page_type=ptype,
                law=cfg["law"],
                required_elements=cfg["required_elements"],
                content=content,
                prompt_hint=cfg["prompt_hint"],
            )
            pc.claude_analysis = result.get("summary", "")
            pc.content_ok = bool(result.get("compliant"))

            for iss in result.get("issues", []):
                if not iss.get("issue"):
                    continue
                try:
                    sev = Severity(iss.get("severity", "warning"))
                except ValueError:
                    sev = Severity.WARNING
                pc.issues.append(LegalIssue(
                    severity=sev,
                    category=ptype,
                    issue=iss["issue"],
                    recommendation=iss.get("recommendation", ""),
                ))

            for missing in result.get("missing_elements", []):
                pc.issues.append(LegalIssue(
                    severity=Severity.WARNING,
                    category=ptype,
                    issue=f"Pflichtangabe fehlt: {missing}",
                    recommendation=f"Ergänze folgende Angabe: {missing}",
                ))
        else:
            if cfg["required"]:
                pc.issues.append(LegalIssue(
                    severity=Severity.CRITICAL,
                    category=ptype,
                    issue=f"{ptype} nicht gefunden",
                    recommendation=(
                        f"Erstelle eine {ptype}-Seite gemäß {cfg['law']} "
                        f"und verlinke sie im Footer jeder Seite."
                    ),
                ))

        page_checks.append(pc)

    # ── 4. Score & summary ───────────────────────────────────────────────
    score, grade = _score(page_checks, cookie_check)

    total_critical = (
        sum(pc.critical_count for pc in page_checks)
        + sum(1 for i in cookie_check.issues if i.severity == Severity.CRITICAL)
    )
    total_warning = (
        sum(pc.warning_count for pc in page_checks)
        + sum(1 for i in cookie_check.issues if i.severity == Severity.WARNING)
    )

    missing_required = [p.name for p in page_checks if not p.found and LEGAL_PAGES[p.name]["required"]]

    summary_lines = [f"**Compliance-Score: {score}/100 — Note {grade}**"]
    if missing_required:
        summary_lines.append(f"⛔ Fehlende Pflichtseiten: {', '.join(missing_required)}")
    if total_critical:
        summary_lines.append(f"🔴 {total_critical} kritische Verstöße")
    if total_warning:
        summary_lines.append(f"🟡 {total_warning} Verbesserungshinweise")
    if not missing_required and total_critical == 0:
        summary_lines.append("✅ Keine kritischen Pflichtfehler gefunden.")

    return ComplianceReport(
        target_url=url,
        page_checks=page_checks,
        cookie_check=cookie_check,
        score=score,
        grade=grade,
        summary="\n".join(summary_lines),
        critical_count=total_critical,
        warning_count=total_warning,
    )
