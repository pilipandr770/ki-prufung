import asyncio
import io
import math
import threading
import pandas as pd
import streamlit as st

from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from config import settings
from scraper.browser import launch_stealth_browser, close_browser
from scraper.page_crawler import crawl_product_site
from scraper.models import ScrapedProduct
from personas.generator import PersonaGenerator
from personas.languages import LANGUAGE_CONFIG, SENTIMENT_LABELS


def run_async(coro):
    """Run an async coroutine in a fresh ProactorEventLoop on a background thread.

    Required on Windows: Streamlit's SelectorEventLoop does not support subprocesses
    (needed by Playwright). We use a ProactorEventLoop in a dedicated thread.
    The Streamlit ScriptRunContext is forwarded so st.* calls (progress bars etc.)
    work correctly from inside the thread.
    """
    result_holder: list = [None]
    exc_holder: list = [None]
    ctx = get_script_run_ctx()  # capture context from the main Streamlit thread

    def _target():
        # Forward Streamlit context so st.* calls work in this thread
        if ctx is not None:
            add_script_run_ctx(threading.current_thread(), ctx)

        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            result_holder[0] = loop.run_until_complete(coro)
        except Exception as e:
            exc_holder[0] = e
        finally:
            # Drain pending tasks and force-GC transports before closing loop.
            # gc.collect() lets Playwright transport __del__ run while loop is still
            # open, preventing the noisy "RuntimeError: Event loop is closed" traceback.
            import gc
            try:
                pending = asyncio.all_tasks(loop)
                if pending:
                    for task in pending:
                        task.cancel()
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.run_until_complete(asyncio.sleep(0))  # flush remaining callbacks
            except Exception:
                pass
            gc.collect()
            gc.collect()  # two passes to catch cyclic refs
            loop.close()

    t = threading.Thread(target=_target)
    t.start()
    t.join()

    if exc_holder[0]:
        raise exc_holder[0]
    return result_holder[0]


from reviews.batch_runner import BatchRunner
from report.builder import build_report_context
from report.renderer import ReportRenderer

st.set_page_config(
    page_title="ConsumerIQ — KI-Marktforschung & EU-Compliance",
    page_icon="🧠",
    layout="wide",
)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Einstellungen")

    # Language selector
    lang_options = {cfg["label"]: code for code, cfg in LANGUAGE_CONFIG.items()}
    selected_label = st.selectbox("🌍 Sprache / Language", options=list(lang_options.keys()))
    language = lang_options[selected_label]

    st.divider()
    max_pages = st.slider("Max. Seiten scrapen", 1, 30, 15)
    batch_size = st.slider("Batch-Größe (API)", 10, 100, 50)
    headless = st.checkbox("Browser im Hintergrund (headless)", value=True)
    st.divider()
    st.caption("API-Key wird aus `.env` geladen.")
    if not settings.anthropic_api_key:
        st.error("ANTHROPIC_API_KEY fehlt in .env!")

# ─── Main Header ──────────────────────────────────────────────────────────────
st.title("🧠 ConsumerIQ — KI-Marktforschung für den EU-Markt")
st.markdown(
    """
    **B2C & B2B Konsumentenforschung, EU-Compliance-Analyse & automatisiertes UX-Testing — in Minuten statt Wochen.**  
    Powered by Claude AI &middot; DSGVO-konform &middot; Kein echtes Nutzertracking &middot; Deutsch, Englisch, Französisch, Polnisch.
    """
)

# ── Value proposition cards ─────────────────────────────────────────────
_c1, _c2, _c3, _c4 = st.columns(4)
_c1.info(
    "🤯 **Konsumenten-Panel** *(B2C & B2B)*  \n"
    "500 KI-Personas beantworten Marktforschungsfragen in 3 Min. — "
    "Konzepttests, Preisanalysen, Werbetests & Konkurrenzvergleiche."
)
_c2.info(
    "⚖️ **EU-Compliance-Check** ✨ *Bonus*  \n"
    "Impressum, DSGVO, Cookie-Banner, AGB & Widerrufsbelehrung — automatisch geprüft. "
    "Bußgelder bis 20 Mio. € vermeiden."
)
_c3.info(
    "🌐 **Produktrezensionen**  \n"
    "Authentische KI-Reviews für Websites, Apps & Produkte — "
    "4 Sprachen, demographisch diverse Personas, CSV/HTML-Export."
)
_c4.info(
    "🧪 **UX-Testing** *(B2C & B2B)*  \n"
    "KI-Personas navigieren mit echtem Browser durch deine App. "
    "B2B-Modus: Firmendaten, USt-IdNr & Adresse werden automatisch generiert."
)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# Shared pipeline: Personas → Reviews → Report
# ══════════════════════════════════════════════════════════════════════════════
def _run_pipeline(product: ScrapedProduct, review_count: int, language: str, batch_size: int) -> None:
    lang_label = LANGUAGE_CONFIG[language]["label"]

    # Phase 1: Personas
    with st.status(f"Schritt 1/3: Personas werden generiert ({lang_label})...", expanded=False) as status:
        gen = PersonaGenerator(language=language)
        personas = gen.generate(review_count)
        status.update(label=f"Schritt 1/3: {len(personas)} Personas generiert ✅", state="complete")

    with st.expander(f"Persona-Vorschau (erste 5 von {len(personas)})"):
        for p in personas[:5]:
            st.markdown(f"**{p.display_name}** — {p.beruf}  \n_Traits: {', '.join(p.trait_labels) or '–'}_")

    # Phase 2: Reviews
    with st.status("Schritt 2/3: KI-Rezensionen werden generiert...", expanded=True) as status:
        progress_bar = st.progress(0)
        progress_text = st.empty()

        def on_progress(done: int, total: int) -> None:
            pct = done / total
            progress_bar.progress(pct)
            progress_text.text(f"{done}/{total} Rezensionen ({pct:.0%})")

        async def _generate(p_list, prod):
            runner = BatchRunner(batch_size=batch_size)
            return await runner.run(p_list, prod, on_progress=on_progress)

        try:
            reviews = run_async(_generate(personas, product))
            status.update(label=f"Schritt 2/3: {len(reviews)} Rezensionen generiert ✅", state="complete")
        except Exception as e:
            st.error(f"Fehler bei Review-Generierung: {e}")
            st.stop()

        if not reviews:
            st.error(
                "⚠️ Es wurden keine Rezensionen generiert — alle API-Aufrufe schlugen fehl.  \n"
                "Mögliche Ursachen: falscher API-Key, Netzwerkfehler, Rate-Limit.  \n"
                "Bitte prüfe den ANTHROPIC_API_KEY in `.env`."
            )
            st.stop()

    # Phase 3: Report
    with st.status("Schritt 3/3: Bericht wird erstellt...", expanded=False) as status:
        ctx = build_report_context(product, reviews, language=language)
        renderer = ReportRenderer()
        html = renderer.render_html(ctx)
        pdf_bytes = renderer.render_pdf(html)
        status.update(label="Schritt 3/3: Bericht fertig ✅", state="complete")

    # ── Results ────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📊 Ergebnisse")


    sl = SENTIMENT_LABELS.get(language, SENTIMENT_LABELS["de"])
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rezensionen", ctx.total_reviews)
    col2.metric("Ø Bewertung", f"{ctx.avg_rating:.1f} ★")
    col3.metric("✅ Positiv", ctx.sentiment_dist.get(sl["positive"], 0))
    col4.metric("❌ Negativ", ctx.sentiment_dist.get(sl["negative"], 0))

    st.components.v1.html(html, height=600, scrolling=True)

    # ── Downloads ──────────────────────────────────────────────────────────
    st.subheader("⬇️ Downloads")
    safe_name = product.name[:30].replace(" ", "_")

    dl1, dl2, dl3 = st.columns(3)
    with dl1:
        st.download_button(
            "📄 HTML-Bericht",
            data=html.encode("utf-8"),
            file_name=f"bericht_{safe_name}.html",
            mime="text/html",
            use_container_width=True,
        )
    with dl2:
        if pdf_bytes:
            st.download_button(
                "📄 PDF-Bericht",
                data=pdf_bytes,
                file_name=f"bericht_{safe_name}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.info("PDF nicht verfügbar (WeasyPrint). Nutze HTML.")
    with dl3:
        csv_buffer = io.StringIO()
        df_export = pd.DataFrame([{
            "id": r.id,
            "persona": r.persona_name,
            "traits": ", ".join(r.persona_traits),
            "stars": r.star_rating,
            "sentiment_score": r.sentiment_score,
            "word_count": r.word_count,
            "review": r.review_text,
            "generated_at": r.generated_at.isoformat(),
        } for r in reviews])
        df_export.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
        st.download_button(
            "📊 CSV-Export (Rohdaten)",
            data=csv_buffer.getvalue().encode("utf-8-sig"),
            file_name=f"reviews_{safe_name}.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ─── Mode Tabs ────────────────────────────────────────────────────────────────
tab_url, tab_direct, tab_research, tab_compliance, tab_test = st.tabs([
    "🌐 Website-URL scrapen",
    "📱 App / Produkt direkt eingeben",
    "🤯 Konsumenten-Panel",
    "⚖️ EU-Compliance prüfen",
    "🧪 App testen (UX-Testing)",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – Website URL Mode
# ══════════════════════════════════════════════════════════════════════════════
with tab_url:
    with st.form("url_form"):
        url = st.text_input(
            "Website oder Produkt-URL",
            placeholder="https://www.otto.de/p/...",
        )
        review_count_url = st.slider(
            "Anzahl Rezensionen", min_value=10, max_value=settings.max_reviews, value=50, step=10,
        )
        st.caption(f"Geschätzte Dauer: ~{math.ceil(review_count_url / 40)} Minute(n)")
        submitted_url = st.form_submit_button("🚀 Analyse starten", use_container_width=True)

    if submitted_url:
        if not url:
            st.error("Bitte eine URL eingeben.")
            st.stop()
        if not settings.anthropic_api_key:
            st.error("ANTHROPIC_API_KEY fehlt in .env!")
            st.stop()

        st.divider()
        # Phase 1: Scraping
        with st.status("Schritt 1/4: Website wird gescrapt...", expanded=True) as status:
            st.write(f"Starte Playwright-Browser (headless={headless})...")

            async def _scrape(u: str, max_p: int) -> ScrapedProduct:
                pw, browser, context = await launch_stealth_browser(headless=headless, language=language)
                try:
                    return await crawl_product_site(context, u, max_pages=max_p)
                finally:
                    await close_browser(pw, browser)

            try:
                product = run_async(_scrape(url, max_pages))
                st.write(f"✅ Produkt erkannt: **{product.name}**")
                if product.price:
                    st.write(f"💶 Preis: {product.price}")
                st.write(f"📄 {len(product.raw_pages)} Seiten gescrapt")
                status.update(label="Schritt 1/4: Scraping abgeschlossen ✅", state="complete")
            except Exception as e:
                st.error(f"Scraping-Fehler: {e}")
                st.stop()

        with st.expander("Produktinfo anzeigen"):
            st.text(product.summary(1200))
            if product.raw_pages:
                st.caption(f"{len(product.raw_pages)} Seiten gescrapt | {len(product.features)} Features gefunden")

        _run_pipeline(product, review_count_url, language, batch_size)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – Direct / App Mode
# ══════════════════════════════════════════════════════════════════════════════
with tab_direct:
    st.markdown(
        "Kein Scraping nötig. Beschreibe das Produkt oder die App direkt — "
        "ideal für Apps (Google Play / App Store), SaaS-Tools und neue Produkte."
    )
    with st.form("direct_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            product_name = st.text_input("Produkt- / App-Name *", placeholder="z. B. MeinShop App")
            category = st.selectbox(
                "Kategorie",
                ["Software / App", "E-Commerce / Website", "Elektronik", "Mode & Fashion",
                 "Essen & Trinken", "Gesundheit & Beauty", "Sport & Outdoor",
                 "Haus & Garten", "Bücher & Medien", "Sonstiges"],
            )
            platform = st.selectbox(
                "Plattform",
                ["Google Play Store", "Apple App Store", "Web-Anwendung",
                 "Desktop-Software", "Website / Onlineshop", "Sonstiges"],
            )
        with col_b:
            price_str = st.text_input("Preis (optional)", placeholder="z. B. 9,99 €/Monat")
            features_raw = st.text_area(
                "Hauptfunktionen (eine pro Zeile)",
                placeholder="Einfache Bedienung\nDatenschutz DSGVO\nMultisprache",
                height=120,
            )

        description = st.text_area(
            "Kurzbeschreibung *",
            placeholder="Beschreibe das Produkt in 2-5 Sätzen. Was macht es? Für wen ist es?",
            height=100,
        )
        review_count_direct = st.slider(
            "Anzahl Rezensionen", min_value=10, max_value=settings.max_reviews, value=50, step=10,
        )
        st.caption(f"Geschätzte Dauer: ~{math.ceil(review_count_direct / 40)} Minute(n)")
        submitted_direct = st.form_submit_button("🚀 Rezensionen generieren", use_container_width=True)

    if submitted_direct:
        if not product_name or not description:
            st.error("Bitte Produktname und Beschreibung ausfüllen.")
            st.stop()
        if not settings.anthropic_api_key:
            st.error("ANTHROPIC_API_KEY fehlt in .env!")
            st.stop()

        features = [f.strip() for f in features_raw.splitlines() if f.strip()]
        product = ScrapedProduct(
            name=product_name,
            description=description,
            price=price_str or None,
            category=f"{category} · {platform}",
            features=features,
        )

        st.divider()
        with st.expander("Produktinfo anzeigen"):
            st.text(product.summary(1200))

        _run_pipeline(product, review_count_direct, language, batch_size)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 – EU Compliance
# ══════════════════════════════════════════════════════════════════════════════
with tab_compliance:
    st.success(
        "✨ **Exklusives Bonus-Feature** — in keinem vergleichbaren Tool enthalten."
    )
    st.markdown(
        """
**Was wird geprüft:**

| Seite | Rechtsgrundlage | Mögliche Folgen bei Verstoß |
|---|---|---|
| Impressum | §5 TMG | Abmahnung ab ~1.000 € |
| Datenschutzerklärung | DSGVO Art. 13/14 | Bußgeld bis **20 Mio. €** oder 4% Jahresumsatz |
| Cookie-Banner | TTDSG §25 | Bußgeld bis 300.000 € |
| AGB | BGB §305 ff. | Unwirksame Klauseln, Haftungsrisiko |
| Widerrufsbelehrung | §355 BGB / EU-RL 2011/83 | Widerrufsfrist verlängert sich auf 12 Monate |

Keine Anmeldung, keine Formulare — vollständig read-only. Läuft in ~60 Sekunden.
        """
    )

    with st.form("compliance_form"):
        comp_url = st.text_input(
            "Website-URL *",
            placeholder="https://meine-firma.de",
        )
        submitted_compliance = st.form_submit_button(
            "⚖️ Compliance prüfen", use_container_width=True
        )

    if submitted_compliance:
        if not comp_url:
            st.error("Bitte eine URL eingeben.")
            st.stop()
        if not settings.anthropic_api_key:
            st.error("ANTHROPIC_API_KEY fehlt in .env!")
            st.stop()

        from compliance.checker import run_compliance_check
        from compliance.models import Severity

        st.divider()
        log_area = st.empty()
        log_lines: list[str] = []

        def _comp_log(msg: str) -> None:
            log_lines.append(msg)
            log_area.text("\n".join(log_lines[-15:]))

        async def _run_compliance():
            pw, browser, ctx = await launch_stealth_browser(
                headless=True, language=language
            )
            try:
                return await run_compliance_check(ctx, comp_url, on_progress=_comp_log)
            finally:
                await close_browser(pw, browser)

        try:
            report = run_async(_run_compliance())
        except Exception as e:
            st.error(f"Compliance-Check fehlgeschlagen: {e}")
            st.stop()

        log_area.empty()

        # ── Score ──────────────────────────────────────────────────────────
        st.subheader("📊 Ergebnis")
        score_color = (
            "normal" if report.score >= 75
            else "inverse" if report.score >= 50
            else "off"
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Score", f"{report.score}/100")
        c2.metric("Note", report.grade)
        c3.metric("🔴 Kritisch", report.critical_count)
        c4.metric("🟡 Warnungen", report.warning_count)
        st.markdown(report.summary)

        st.divider()

        # ── Cookie Banner ─────────────────────────────────────────────────
        if report.cookie_check:
            cb = report.cookie_check
            cb_ok = cb.present and cb.reject_option and not cb.pre_checked_boxes
            with st.expander(
                f"{'✅' if cb_ok else '⚠️'} Cookie-Consent-Banner (TTDSG / DSGVO)",
                expanded=not cb_ok,
            ):
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Banner vorhanden", "✅ Ja" if cb.present else "❌ Nein")
                col_b.metric("Ablehnen möglich", "✅ Ja" if cb.reject_option else "❌ Nein")
                col_c.metric(
                    "Vorausgew. Checkboxen",
                    "🔴 Ja (DSGVO-Verstoß!)" if cb.pre_checked_boxes else "✅ Nein",
                )
                if cb.claude_analysis:
                    st.info(cb.claude_analysis)
                for iss in cb.issues:
                    icon = "🔴" if iss.severity == Severity.CRITICAL else "🟡"
                    st.markdown(f"{icon} **{iss.issue}**  \n→ _{iss.recommendation}_")
                if cb.screenshot_b64:
                    import base64 as _b64
                    st.image(
                        _b64.b64decode(cb.screenshot_b64),
                        caption="Screenshot beim Erstbesuch (Cookie-Banner-Status)",
                    )

        # ── Per-page results ──────────────────────────────────────────────
        st.subheader("📄 Rechtsseiten")
        for pc in report.page_checks:
            if not pc.found:
                icon = "❌"
            elif pc.critical_count > 0:
                icon = "🔴"
            elif pc.warning_count > 0:
                icon = "🟡"
            else:
                icon = "✅"

            with st.expander(
                f"{icon} {pc.name} ({pc.law_basis})",
                expanded=(not pc.found or pc.critical_count > 0),
            ):
                if pc.found:
                    st.caption(f"URL: {pc.url}")
                    if pc.claude_analysis:
                        st.info(pc.claude_analysis)
                    if pc.issues:
                        for iss in pc.issues:
                            sev_icon = "🔴" if iss.severity == Severity.CRITICAL else "🟡"
                            st.markdown(
                                f"{sev_icon} **{iss.issue}**  \n→ _{iss.recommendation}_"
                            )
                    else:
                        st.success("Keine Probleme gefunden.")
                else:
                    st.error(
                        f"{pc.name} nicht gefunden.  \n"
                        + (pc.issues[0].recommendation if pc.issues else "")
                    )

        # ── Download ──────────────────────────────────────────────────────
        st.divider()
        domain = comp_url.split("//")[-1].split("/")[0]
        st.download_button(
            "📄 Compliance-Bericht herunterladen (Markdown)",
            data=report.to_markdown().encode("utf-8"),
            file_name=f"compliance_{domain}.md",
            mime="text/markdown",
            use_container_width=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 – AI UX Testing
# ══════════════════════════════════════════════════════════════════════════════
with tab_test:
    st.markdown(
        "**KI-Personas registrieren sich auf deiner App, testen die UX und löschen sich danach.**  \n"
        "Ideal für DSGVO-Compliance-Tests, Onboarding-Analyse, und vollständige UX-Audits."
    )

    # ── IMAP status indicator ──────────────────────────────────────────────
    if settings.imap_configured:
        st.success(
            f"✅ E-Mail-Infrastruktur aktiv: `{settings.imap_user}` · "
            f"IMAP: `{settings.imap_host}:{settings.imap_port}`"
        )
    else:
        st.warning(
            "⚠️ IMAP nicht konfiguriert — E-Mail-Verifizierung deaktiviert.  \n"
            "Füge IMAP_HOST und IMAP_PASSWORD zu `.env` hinzu, um E-Mail-Bestätigungen zu nutzen."
        )

    # ── Test configuration form ───────────────────────────────────────────
    with st.form("test_form"):
        test_url = st.text_input(
            "Ziel-URL *",
            placeholder="https://meine-app.de",
        )

        default_steps = (
            "Registriere einen neuen Account mit der Persona-E-Mail und dem Passwort\n"
            "Bestätige die Registrierung über den Verifizierungslink in der E-Mail\n"
            "Melde dich mit den registrierten Zugangsdaten an\n"
            "Navigiere zur Profilseite oder zu den Einstellungen\n"
            "Lösche den Account (DSGVO-Recht auf Löschung testen)"
        )
        steps_raw = st.text_area(
            "Testschritte (einer pro Zeile)",
            value=default_steps,
            height=160,
        )

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            test_persona_count = st.slider("Anzahl Testpersonas", min_value=1, max_value=5, value=2)
        with col_t2:
            auto_delete = st.checkbox(
                "Account automatisch löschen (Auto-Delete)",
                value=True,
                help="Sucht und klickt den 'Account löschen'-Button am Ende jedes Tests.",
            )
        test_headless = st.checkbox("Browser im Hintergrund (headless)", value=True)

        test_mode = st.radio(
            "🏢 Zielpublikum",
            ["B2C — Privatkunden", "B2B — Geschäftskunden"],
            horizontal=True,
            help="B2B: Personas erhalten automatisch Firmendaten, USt-IdNr & Adresse.",
        )

        submitted_test = st.form_submit_button("▶️ Test starten", use_container_width=True)

    if submitted_test:
        if not test_url:
            st.error("Bitte eine Ziel-URL eingeben.")
            st.stop()
        if not settings.anthropic_api_key:
            st.error("ANTHROPIC_API_KEY fehlt in .env!")
            st.stop()

        steps = [s.strip() for s in steps_raw.splitlines() if s.strip()]
        if not steps:
            st.error("Bitte mindestens einen Testschritt angeben.")
            st.stop()

        _mode = "b2b" if "B2B" in test_mode else "b2c"

        from testing.models import TestScenario
        from testing.engine import run_test_session

        scenario = TestScenario(
            target_url=test_url,
            steps=steps,
            auto_delete=auto_delete,
            language=language,
            mode=_mode,
        )

        # Generate test personas
        gen = PersonaGenerator(language=language, mode=_mode)
        test_personas = gen.generate(test_persona_count)

        st.divider()
        st.subheader("🤖 Testpersonas")
        for p in test_personas:
            st.markdown(
                f"**{p.display_name}** — {p.beruf}  \n"
                f"E-Mail: `{p.email}` · Passwort: `{p.password}`  \n"
                f"_Traits: {', '.join(p.trait_labels) or '–'}_"
            )
            if p.mode == "b2b" and p.company_name:
                st.markdown(
                    f"🏢 **{p.company_name} {p.rechtsform}** · USt-IdNr: `{p.vat_number}`  \n"
                    f"📍 {p.company_address}, {p.company_zip} {p.company_city}"
                )

        st.divider()
        st.subheader("🔄 Testablauf")
        log_area = st.empty()
        log_lines: list[str] = []

        def _on_progress(msg: str) -> None:
            log_lines.append(msg)
            log_area.text("\n".join(log_lines[-20:]))  # show last 20 lines

        async def _run_tests():
            return await run_test_session(
                scenario,
                test_personas,
                headless=test_headless,
                on_progress=_on_progress,
            )

        try:
            session = run_async(_run_tests())
        except Exception as e:
            st.error(f"Testfehler: {e}")
            st.stop()

        # ── Results display ────────────────────────────────────────────────
        st.divider()
        st.subheader("📊 Testergebnisse")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Personas getestet", session.total_personas)
        m2.metric("Registrierungen ✅", session.successful_registrations)
        m3.metric("Accounts gelöscht 🗑️", session.successful_deletions)
        m4.metric("DSGVO-Probleme ⚠️", len(session.all_dsgvo_issues))

        if session.all_dsgvo_issues:
            with st.expander("⚠️ DSGVO-Probleme im Detail"):
                for persona_name, step in session.all_dsgvo_issues:
                    st.markdown(
                        f"**{persona_name}** — Schritt {step.step_index + 1}: "
                        f"{step.step_description}  \n{step.claude_analysis}"
                    )

        for run in session.persona_runs:
            with st.expander(
                f"{'✅' if run.passed_steps == len(run.results) else '⚠️'} "
                f"{run.persona_display} — {run.passed_steps}/{len(run.results)} Schritte OK"
            ):
                st.markdown(f"**E-Mail:** `{run.persona_email}`")
                st.markdown(f"**Registriert:** {'✅' if run.registered else '❌'}  "
                            f"**Gelöscht:** {'✅' if run.deleted else '❌'}")
                st.markdown("**Gesamturteil:**")
                st.info(run.overall_verdict)

                st.markdown("---")
                for step in run.results:
                    status_icon = {
                        "passed": "✅", "failed": "❌", "skipped": "⏭️",
                        "pending": "⏳", "running": "🔄",
                    }.get(step.status.value, "❓")
                    # Streamlit forbids nested expanders — use a bordered container instead
                    with st.container(border=True):
                        st.markdown(
                            f"{status_icon} **Schritt {step.step_index + 1}:** {step.step_description}"
                        )
                        if step.claude_analysis:
                            st.markdown(step.claude_analysis)
                        if step.error:
                            st.error(f"Fehler: {step.error}")
                        if step.screenshot_b64:
                            import base64 as _b64
                            img_bytes = _b64.b64decode(step.screenshot_b64)
                            st.image(img_bytes, caption=f"Screenshot Schritt {step.step_index + 1}")

        # ── Session summary markdown download ──────────────────────────────
        st.divider()
        st.subheader("⬇️ Bericht")
        st.download_button(
            "📄 UX-Bericht herunterladen (Markdown)",
            data=session.summary.encode("utf-8"),
            file_name=f"ux_test_{test_url.split('//')[-1].split('/')[0]}.md",
            mime="text/markdown",
            use_container_width=True,
        )
        st.markdown(session.summary)

# ══════════════════════════════════════════════════════════════════════════════
# TAB – Synthetic Consumer Panel
# ══════════════════════════════════════════════════════════════════════════════
with tab_research:
    from research.models import RESEARCH_TEMPLATES, QuestionType

    st.markdown(
        "Ähnlich wie **Aaru** ($1B AI-Startup): Tausende KI-Personas beantworten strukturierte "
        "Marktforschungsfragen.  \n"
        "Kein Browser, keine Formulare — nur authentische, demographisch diverse "
        "Konsumentenmeinungen in Minuten statt Wochen."
    )

    with st.form("research_form"):
        tmpl_options = {v["label"]: k for k, v in RESEARCH_TEMPLATES.items()}
        tmpl_label = st.selectbox(
            "📊 Forschungsmethode",
            options=list(tmpl_options.keys()),
        )
        tmpl_key = tmpl_options[tmpl_label]
        st.caption(RESEARCH_TEMPLATES[tmpl_key]["description"])

        prod_desc_research = st.text_area(
            "Produkt / Konzept / Werbebotschaft *",
            placeholder=(
                "Beschreibe dein Produkt, deine Idee oder die zu testende Botschaft "
                "ausführlich. Je mehr Details, desto realistischere Antworten."
            ),
            height=130,
        )

        extra_ctx = st.text_area(
            "Vergleichsprodukt / Zusätzlicher Kontext (optional)",
            placeholder="z.B.: Konkurrenzprodukt B ist ... / Preisbenchmark: 19€/Monat",
            height=70,
        )

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            panel_size = st.slider(
                "Panel-Größe (Anzahl Personas)",
                min_value=20, max_value=500, value=50, step=10,
            )
        with col_r2:
            st.markdown(f"""
            **Fragen im Fragebogen:** {len(RESEARCH_TEMPLATES[tmpl_key]['questions'])}

            **Geschätzte Kosten:** ~{panel_size * len(RESEARCH_TEMPLATES[tmpl_key]['questions']) * 0.0002:.2f} USD
            """)

        submitted_research = st.form_submit_button(
            "🤯 Panel starten", use_container_width=True
        )

    if submitted_research:
        if not prod_desc_research.strip():
            st.error("Bitte Produkt/Konzept beschreiben.")
            st.stop()
        if not settings.anthropic_api_key:
            st.error("ANTHROPIC_API_KEY fehlt in .env!")
            st.stop()

        from research.runner import run_research_panel

        gen = PersonaGenerator(language=language)
        research_personas = gen.generate(panel_size)

        st.divider()
        log_area_r = st.empty()
        rlog: list[str] = []

        def _rlog(msg: str) -> None:
            rlog.append(msg)
            log_area_r.text("\n".join(rlog[-12:]))

        async def _run_research():
            return await run_research_panel(
                research_personas,
                prod_desc_research,
                tmpl_key,
                extra_context=extra_ctx,
                on_progress=_rlog,
                concurrency=settings.max_concurrent_batches,
            )

        try:
            report = run_async(_run_research())
        except Exception as e:
            st.error(f"Panel-Fehler: {e}")
            st.stop()

        log_area_r.empty()

        # ── Executive Summary ─────────────────────────────────────────────
        st.subheader("📊 Panel-Ergebnisse")
        st.info(report.executive_summary)

        st.divider()

        # ── Per-question results ────────────────────────────────────────
        for ins in report.insights:
            with st.expander(f"💬 {ins.question_text}", expanded=True):

                if ins.avg_score is not None:
                    # Score bar chart
                    import plotly.express as px
                    dist = ins.score_distribution or {}
                    if dist:
                        df_dist = {"Score": list(dist.keys()), "Anzahl": list(dist.values())}
                        fig = px.bar(
                            df_dist, x="Score", y="Anzahl",
                            color="Score",
                            color_continuous_scale="RdYlGn",
                            range_color=[1, 10],
                            title=f"Ø Score: {ins.avg_score:.1f} / 10",
                            height=220,
                        )
                        fig.update_layout(margin=dict(t=40, b=10), showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)

                if ins.avg_price is not None:
                    p = ins.price_percentiles or {}
                    cols = st.columns(4)
                    cols[0].metric("Ø Preis", f"{ins.avg_price:.2f} €")
                    if p:
                        cols[1].metric("P25 (günstig)", f"{p.get('P25', 0):.2f} €")
                        cols[2].metric("P50 (Median)", f"{p.get('P50', 0):.2f} €")
                        cols[3].metric("P75 (teuer)", f"{p.get('P75', 0):.2f} €")

                if ins.choice_counts:
                    import plotly.express as px
                    df_choice = {
                        "Option": list(ins.choice_counts.keys()),
                        "Stimmen": list(ins.choice_counts.values()),
                    }
                    fig = px.pie(
                        df_choice, names="Option", values="Stimmen",
                        title="Verteilung", height=240,
                    )
                    fig.update_layout(margin=dict(t=40, b=10))
                    st.plotly_chart(fig, use_container_width=True)

                if ins.claude_summary:
                    st.markdown(ins.claude_summary)

                if ins.sample_quotes:
                    st.markdown("**Stimmen aus dem Panel:**")
                    for q_text in ins.sample_quotes[:10]:
                        st.markdown(f'> "{q_text}"')

        # ── Download ──────────────────────────────────────────────────────
        st.divider()
        st.download_button(
            "📄 Forschungsbericht herunterladen (Markdown)",
            data=report.to_markdown().encode("utf-8"),
            file_name=f"panel_{tmpl_key}_{panel_size}personas.md",
            mime="text/markdown",
            use_container_width=True,
        )

