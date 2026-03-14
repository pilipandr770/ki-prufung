"""
Claude Vision step evaluator.

For each completed test step we send Claude:
  • the screenshot (base64 PNG)
  • a short HTML snippet (optional)
  • the step description
  • the persona profile

Claude returns a JSON object with:
  {
    "analysis": "Natural language description of what happened",
    "passed": true | false,
    "dsgvo_flag": true | false,
    "dsgvo_note": "Optional explanation if dsgvo_flag is true"
  }
"""
from __future__ import annotations

import json
import re
from typing import Optional

import anthropic

from config import settings
from personas.models import Persona
from .models import StepResult, StepStatus

_SYSTEM_DE = """Du bist ein erfahrener UX-Tester und Datenschutzexperte.
Du analysierst Screenshots von Web-Applikationen aus der Perspektive einer bestimmten Testperson.
Antworte ausschließlich mit einem validen JSON-Objekt — kein Prosa, keine Erklärungen außerhalb des JSON."""

_SYSTEM_EN = """You are an experienced UX tester and data-privacy expert.
You analyse screenshots of web applications from the perspective of a specific test persona.
Respond ONLY with a valid JSON object — no prose, no text outside the JSON."""

_SYSTEM_MAP = {"de": _SYSTEM_DE, "en": _SYSTEM_EN, "fr": _SYSTEM_EN, "pl": _SYSTEM_EN}

_USER_TEMPLATE_DE = """Testperson: {display_name}
Beruf: {beruf}
Eigenschaften: {traits}
Schritt: {step_description}

{html_block}

Analysiere den Screenshot und bewerte:
1. Wurde der Schritt erfolgreich abgeschlossen?
2. Gibt es UX-Probleme (Verwirrung, fehlende Informationen, schlechte Zugänglichkeit)?
3. Gibt es DSGVO-Probleme (fehlende Einwilligung, unklare Datenweitergabe-Hinweise, fehlende Löschmöglichkeit)?

Antworte mit folgendem JSON (ersetze nichts, alle Felder müssen vorhanden sein):
{{
  "analysis": "Kurze Beschreibung in 2-3 Sätzen was auf dem Screenshot zu sehen ist und wie der Schritt gelaufen ist",
  "passed": true,
  "dsgvo_flag": false,
  "dsgvo_note": ""
}}"""

_USER_TEMPLATE_EN = """Test persona: {display_name}
Job: {beruf}
Traits: {traits}
Step: {step_description}

{html_block}

Analyse the screenshot and evaluate:
1. Was the step completed successfully?
2. Are there UX issues (confusion, missing info, poor accessibility)?
3. Are there GDPR/privacy issues (missing consent, unclear data sharing, no deletion option)?

Respond with this JSON (all fields must be present):
{{
  "analysis": "2-3 sentence description of what the screenshot shows and how the step went",
  "passed": true,
  "dsgvo_flag": false,
  "dsgvo_note": ""
}}"""

_USER_TEMPLATE_MAP = {"de": _USER_TEMPLATE_DE, "en": _USER_TEMPLATE_EN,
                      "fr": _USER_TEMPLATE_EN, "pl": _USER_TEMPLATE_EN}


def _parse_response(text: str) -> dict:
    """Extract the first JSON object from Claude's response."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"analysis": text.strip(), "passed": False, "dsgvo_flag": False, "dsgvo_note": ""}


def evaluate_step(
    step_result: StepResult,
    persona: Persona,
    language: str = "de",
) -> StepResult:
    """
    Call Claude Vision to evaluate *step_result* and update it in-place.

    Requires *step_result.screenshot_b64* to be non-empty.
    Returns the same *step_result* object with ``claude_analysis``,
    ``dsgvo_flag``, and ``status`` populated.
    """
    if not step_result.screenshot_b64:
        step_result.claude_analysis = "No screenshot available."
        step_result.status = StepStatus.SKIPPED
        return step_result

    system_prompt = _SYSTEM_MAP.get(language, _SYSTEM_EN)
    tmpl = _USER_TEMPLATE_MAP.get(language, _USER_TEMPLATE_EN)
    html_block = (
        f"Relevant HTML:\n```html\n{step_result.html_snippet[:1500]}\n```"
        if step_result.html_snippet
        else ""
    )
    user_text = tmpl.format(
        display_name=persona.display_name,
        beruf=persona.beruf,
        traits=", ".join(persona.trait_labels) or "—",
        step_description=step_result.step_description,
        html_block=html_block,
    )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": step_result.screenshot_b64,
                            },
                        },
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        )
        parsed = _parse_response(response.content[0].text)
    except Exception as exc:
        parsed = {
            "analysis": f"Evaluation error: {exc}",
            "passed": False,
            "dsgvo_flag": False,
            "dsgvo_note": "",
        }

    step_result.claude_analysis = parsed.get("analysis", "")
    step_result.dsgvo_flag = bool(parsed.get("dsgvo_flag", False))
    if parsed.get("dsgvo_note"):
        step_result.claude_analysis += f"\n⚠️ DSGVO: {parsed['dsgvo_note']}"
    step_result.status = StepStatus.PASSED if parsed.get("passed") else StepStatus.FAILED
    return step_result


def generate_overall_verdict(
    persona_run,  # PersonaTestRun — avoid circular import
    language: str = "de",
) -> str:
    """
    Ask Claude for a holistic UX verdict based on all step analyses.
    Returns a markdown-formatted summary string.
    """
    steps_text = "\n".join(
        f"Step {r.step_index + 1} ({r.status.value}): {r.claude_analysis}"
        for r in persona_run.results
    )
    dsgvo_summary = (
        f"\nDSGVO issues found in steps: "
        + ", ".join(str(r.step_index + 1) for r in persona_run.dsgvo_issues)
        if persona_run.dsgvo_issues
        else ""
    )

    if language == "de":
        prompt = (
            f"Testperson: {persona_run.persona_display}\n\n"
            f"Ergebnisse aller Schritte:\n{steps_text}{dsgvo_summary}\n\n"
            "Schreibe ein kurzes UX-Gesamturteil (max. 5 Sätze) mit konkreten Verbesserungsvorschlägen."
        )
    else:
        prompt = (
            f"Test persona: {persona_run.persona_display}\n\n"
            f"All step results:\n{steps_text}{dsgvo_summary}\n\n"
            "Write a brief overall UX verdict (max. 5 sentences) with concrete improvement suggestions."
        )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        return f"Verdict generation failed: {exc}"
