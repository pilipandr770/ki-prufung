"""
High-level testing engine — orchestrates runner + evaluator for all personas.

Usage::

    from testing.engine import run_test_session
    from testing.models import TestScenario

    scenario = TestScenario(
        target_url="https://example.com",
        steps=[
            "Register a new account using the persona email and password",
            "Confirm registration via the verification email",
            "Log in with the registered credentials",
            "Navigate to settings and delete the account",
        ],
    )
    session = await run_test_session(scenario, personas, on_progress=callback)
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

from personas.models import Persona
from .models import TestScenario, TestSession, PersonaTestRun, StepStatus
from .runner import run_persona_test
from .evaluator import evaluate_step, generate_overall_verdict


async def run_test_session(
    scenario: TestScenario,
    personas: list[Persona],
    *,
    headless: bool = True,
    on_progress: Optional[Callable[[str], None]] = None,
) -> TestSession:
    """
    Run *scenario* for each persona sequentially (to avoid IP blocks).
    Calls *on_progress* with status strings suitable for display in the UI.

    Returns a fully populated :class:`TestSession`.
    """
    session = TestSession(scenario=scenario)

    def _log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    for i, persona in enumerate(personas, 1):
        _log(f"[{i}/{len(personas)}] Starte Test für {persona.display_name} …")

        # 1. Browser interaction
        persona_run: PersonaTestRun = await run_persona_test(
            persona, scenario, headless=headless
        )

        # 2. Claude Vision evaluation for each step
        for step_result in persona_run.results:
            if step_result.screenshot_b64:
                _log(
                    f"  Schritt {step_result.step_index + 1} auswerten …"
                )
                evaluate_step(step_result, persona, language=scenario.language)

        # 3. Overall verdict
        _log(f"  Gesamturteil für {persona.display_name} generieren …")
        persona_run.overall_verdict = generate_overall_verdict(
            persona_run, language=scenario.language
        )

        session.persona_runs.append(persona_run)
        _log(
            f"  ✓ {persona.display_name}: "
            f"{persona_run.passed_steps} / {len(persona_run.results)} Schritte OK"
            + (f", {len(persona_run.dsgvo_issues)} DSGVO-Probleme" if persona_run.dsgvo_issues else "")
        )

    # 4. Session-level summary
    session.summary = _build_session_summary(session)
    return session


def _build_session_summary(session: TestSession) -> str:
    total = session.total_personas
    regs = session.successful_registrations
    dels = session.successful_deletions
    dsgvo = len(session.all_dsgvo_issues)
    lines = [
        f"## Testergebnis",
        f"- {total} Personas getestet",
        f"- {regs}/{total} Registrierungen erfolgreich",
        f"- {dels}/{total} Accounts gelöscht",
    ]
    if dsgvo:
        lines.append(f"- ⚠️ {dsgvo} DSGVO-Probleme gefunden")
    for persona_run in session.persona_runs:
        status = "✅" if persona_run.passed_steps == len(persona_run.results) else "⚠️"
        lines.append(
            f"\n### {status} {persona_run.persona_display}"
        )
        lines.append(persona_run.overall_verdict)
    return "\n".join(lines)
