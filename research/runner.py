"""
Synthetic Consumer Panel runner.

Each persona answers a structured research questionnaire via Claude.
No browser, no forms — pure LLM simulation of consumer opinions.
Scales to thousands of personas with async batch processing.
"""
from __future__ import annotations

import asyncio
import json
import re
import statistics
from typing import Callable, Optional

import anthropic

from config import settings
from personas.models import Persona
from .models import (
    PersonaResponse, AggregatedInsight, ResearchReport,
    QuestionType, RESEARCH_TEMPLATES,
)


# ── Per-persona survey call ───────────────────────────────────────────────────

_SYSTEM = (
    "Du bist eine reale Person mit konkreten Eigenschaften, Erfahrungen und Meinungen. "
    "Antworte auf Marktforschungsfragen ausschliesslich aus deiner persönlichen Perspektive — "
    "authentisch, manchmal widersprüchlich, nie übertrieben positiv. "
    "Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt."
)


def _build_survey_prompt(
    persona: Persona,
    product_description: str,
    questions: list[dict],
    extra_context: str = "",
) -> str:
    q_lines = []
    for q in questions:
        if q["type"] == "choice":
            opts = " / ".join(q.get("options", []))
            q_lines.append(f'  "{q["id"]}": {q["text"]} Optionen: {opts}')
        elif q["type"] == "scale":
            q_lines.append(f'  "{q["id"]}": {q["text"]} (Antwort: Zahl 1-10)')
        elif q["type"] == "price":
            q_lines.append(f'  "{q["id"]}": {q["text"]} (Antwort: Zahl in EUR, z.B. 29.99)')
        else:
            q_lines.append(f'  "{q["id"]}": {q["text"]} (Antwort: 1-2 Sätze Text)')

    json_keys = "\n".join(f'  "{q["id"]}": <wert>' for q in questions)

    return (
        f"Du bist: {persona.display_name}\n"
        f"Beruf: {persona.beruf}\n"
        f"Eigenschaften: {', '.join(persona.trait_labels) or 'keine besonderen'}\n\n"
        f"Produkt/Konzept:\n{product_description[:1200]}\n"
        + (f"\nZusätzlicher Kontext: {extra_context}\n" if extra_context else "")
        + f"\nFragebogen:\n"
        + "\n".join(q_lines)
        + "\n\nAntworte mit diesem JSON:\n{\n"
        + json_keys
        + "\n}"
    )


def _parse_response(text: str, questions: list[dict]) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        raw = json.loads(m.group())
    except json.JSONDecodeError:
        return {}

    cleaned: dict = {}
    for q in questions:
        val = raw.get(q["id"])
        if val is None:
            continue
        if q["type"] in ("scale", "price"):
            try:
                cleaned[q["id"]] = float(str(val).replace(",", ".").replace("€", "").strip())
            except (ValueError, AttributeError):
                pass
        elif q["type"] == "choice":
            cleaned[q["id"]] = str(val)
        else:
            cleaned[q["id"]] = str(val)
    return cleaned


async def _ask_persona(
    persona: Persona,
    product_description: str,
    questions: list[dict],
    semaphore: asyncio.Semaphore,
    extra_context: str = "",
) -> PersonaResponse:
    prompt = _build_survey_prompt(persona, product_description, questions, extra_context)
    async with semaphore:
        try:
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            resp = await client.messages.create(
                model=settings.claude_model,
                max_tokens=500,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            answers = _parse_response(resp.content[0].text, questions)
        except Exception:
            answers = {}

    return PersonaResponse(
        persona_id=persona.id,
        persona_display=persona.display_name,
        persona_traits=persona.trait_labels,
        persona_age=persona.alter,
        persona_region=persona.bundesland,
        answers=answers,
    )


# ── Aggregation ───────────────────────────────────────────────────────────────

def _aggregate_question(
    q_id: str,
    q_text: str,
    q_type: str,
    responses: list[PersonaResponse],
    options: list[str] | None = None,
) -> AggregatedInsight:
    qtype = QuestionType(q_type)
    values = [r.answers.get(q_id) for r in responses if q_id in r.answers]
    insight = AggregatedInsight(
        question_id=q_id,
        question_text=q_text,
        question_type=qtype,
    )

    if qtype == QuestionType.SCALE and values:
        nums = [v for v in values if isinstance(v, (int, float))]
        if nums:
            insight.avg_score = round(statistics.mean(nums), 2)
            dist: dict[int, int] = {}
            for v in nums:
                k = int(round(v))
                dist[k] = dist.get(k, 0) + 1
            insight.score_distribution = dist

    elif qtype == QuestionType.PRICE and values:
        nums = [v for v in values if isinstance(v, (int, float)) and 0 < v < 100_000]
        if nums:
            insight.avg_price = round(statistics.mean(nums), 2)
            sorted_nums = sorted(nums)
            n = len(sorted_nums)
            insight.price_percentiles = {
                "P25": round(sorted_nums[n // 4], 2),
                "P50": round(sorted_nums[n // 2], 2),
                "P75": round(sorted_nums[3 * n // 4], 2),
            }

    elif qtype == QuestionType.MULTIPLE_CHOICE and values:
        counts: dict[str, int] = {}
        for v in values:
            counts[str(v)] = counts.get(str(v), 0) + 1
        insight.choice_counts = counts

    elif qtype == QuestionType.OPEN and values:
        # Store top sample quotes for Claude synthesis (done separately)
        insight.sample_quotes = [str(v) for v in values if v][:20]

    return insight


def _synthesize_open_question(q_text: str, answers: list[str]) -> str:
    """Ask Claude to extract themes and summarize open-text answers."""
    if not answers:
        return ""
    joined = "\n".join(f"- {a}" for a in answers[:40])
    prompt = (
        f"Frage: {q_text}\n\n"
        f"Antworten von {len(answers)} Konsumenten:\n{joined}\n\n"
        "Fasse in 3-4 Sätzen zusammen: welche Themen, Bedenken und Wünsche dominierten? "
        "Keine Aufzählung, fließender Text auf Deutsch."
    )
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception:
        return ""


def _generate_executive_summary(
    template_name: str,
    product_description: str,
    insights: list[AggregatedInsight],
    persona_count: int,
) -> str:
    parts = [f"Panel-Größe: {persona_count} Personas. Methode: {template_name}."]
    for ins in insights:
        if ins.avg_score is not None:
            parts.append(f"{ins.question_text}: Ø {ins.avg_score:.1f}/10.")
        if ins.avg_price is not None:
            parts.append(f"{ins.question_text}: Ø {ins.avg_price:.2f} EUR.")
        if ins.choice_counts:
            top = max(ins.choice_counts, key=lambda k: ins.choice_counts[k])  # type: ignore
            parts.append(f"{ins.question_text}: Mehrheit wählte '{top}'.")
        if ins.claude_summary:
            parts.append(ins.claude_summary)

    context = "\n".join(parts)
    prompt = (
        f"Produkt/Konzept: {product_description[:600]}\n\n"
        f"Forschungsergebnisse:\n{context}\n\n"
        "Schreibe einen Executive Summary (5-7 Sätze) auf Deutsch mit den wichtigsten "
        "Erkenntnissen für das Management. Fokus: Kaufbereitschaft, Hauptbedenken, "
        "wichtigste Handlungsempfehlung."
    )
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception:
        return context


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_research_panel(
    personas: list[Persona],
    product_description: str,
    template_key: str,
    *,
    extra_context: str = "",
    on_progress: Optional[Callable[[str], None]] = None,
    concurrency: int = 8,
) -> ResearchReport:
    def _log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    template = RESEARCH_TEMPLATES[template_key]
    questions = template["questions"]
    _log(f"Panel gestartet: {len(personas)} Personas, {len(questions)} Fragen...")

    sem = asyncio.Semaphore(concurrency)
    tasks = [
        _ask_persona(p, product_description, questions, sem, extra_context)
        for p in personas
    ]

    responses: list[PersonaResponse] = []
    for i, coro in enumerate(asyncio.as_completed(tasks), 1):
        r = await coro
        responses.append(r)
        if i % 10 == 0 or i == len(tasks):
            _log(f"  {i}/{len(tasks)} Antworten gesammelt...")

    _log("Aggregiere Ergebnisse...")
    insights: list[AggregatedInsight] = []
    for q in questions:
        ins = _aggregate_question(
            q["id"], q["text"], q["type"], responses,
            options=q.get("options"),
        )
        if q["type"] == "open" and ins.sample_quotes:
            _log(f"  Themen aus offenen Antworten für '{q['id']}' extrahieren...")
            ins.claude_summary = _synthesize_open_question(q["text"], ins.sample_quotes)
        insights.append(ins)

    _log("Executive Summary wird generiert...")
    summary = _generate_executive_summary(
        template["label"], product_description, insights, len(personas)
    )

    _log(f"Fertig. {len(responses)}/{len(personas)} valide Antworten.")
    return ResearchReport(
        template_name=template["label"],
        product_description=product_description,
        persona_count=len(personas),
        responses=responses,
        insights=insights,
        executive_summary=summary,
    )
