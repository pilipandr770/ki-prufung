"""Data models for the synthetic consumer panel / market research engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QuestionType(str, Enum):
    SCALE = "scale"           # 1-10 numeric score
    MULTIPLE_CHOICE = "choice"  # pick one from options
    OPEN = "open"             # free-text answer
    PRICE = "price"           # willingness-to-pay


# ── Built-in research templates ───────────────────────────────────────────────

RESEARCH_TEMPLATES: dict[str, dict] = {
    "concept_test": {
        "label": "Konzepttest (Produktidee bewerten)",
        "description": "Bewertet, ob eine neue Produktidee kaufwürdig ist.",
        "questions": [
            {
                "id": "interest",
                "type": "scale",
                "text": "Wie interessant findest du dieses Produkt? (1 = gar nicht, 10 = sehr)",
            },
            {
                "id": "buy_intent",
                "type": "scale",
                "text": (
                    "Wie wahrscheinlich würdest du dieses Produkt kaufen? "
                    "(1 = definitiv nicht, 10 = definitiv ja)"
                ),
            },
            {
                "id": "main_concern",
                "type": "open",
                "text": "Was ist dein größter Einwand oder deine größte Sorge bezüglich dieses Produkts?",
            },
            {
                "id": "main_benefit",
                "type": "open",
                "text": "Was ist der wichtigste Vorteil dieses Produkts für dich persönlich?",
            },
            {
                "id": "wtp",
                "type": "price",
                "text": "Was wäre für dich ein fairer Preis für dieses Produkt?",
            },
        ],
    },
    "ad_test": {
        "label": "Anzeigentest (Marketing-Botschaft testen)",
        "description": "Vergleicht bis zu 3 Werbebotschaften oder Slogans.",
        "questions": [
            {
                "id": "attention",
                "type": "scale",
                "text": "Wie sehr erregt diese Werbebotschaft deine Aufmerksamkeit? (1-10)",
            },
            {
                "id": "believability",
                "type": "scale",
                "text": "Wie glaubwürdig findest du diese Aussage? (1-10)",
            },
            {
                "id": "relevance",
                "type": "scale",
                "text": "Wie relevant ist diese Botschaft für dich persönlich? (1-10)",
            },
            {
                "id": "reaction",
                "type": "open",
                "text": "Welche Reaktion oder welches Gefühl löst diese Werbung bei dir aus?",
            },
        ],
    },
    "competitor_comparison": {
        "label": "Konkurrenzvergleich",
        "description": "Vergleicht dein Produkt mit einem Wettbewerber.",
        "questions": [
            {
                "id": "preference",
                "type": "choice",
                "text": "Welches Produkt würdest du bevorzugen?",
                "options": ["Produkt A", "Produkt B", "Keines von beiden"],
            },
            {
                "id": "switch_reason",
                "type": "open",
                "text": "Was müsste Produkt B anders machen, damit du zu ihm wechselst?",
            },
            {
                "id": "a_strength",
                "type": "open",
                "text": "Was ist der größte Vorteil von Produkt A gegenüber Produkt B?",
            },
            {
                "id": "b_strength",
                "type": "open",
                "text": "Was ist der größte Vorteil von Produkt B gegenüber Produkt A?",
            },
        ],
    },
    "price_sensitivity": {
        "label": "Preissensitivitätsanalyse (Van Westendorp)",
        "description": "Findet den optimalen Preispunkt nach Van-Westendorp-Methode.",
        "questions": [
            {
                "id": "too_cheap",
                "type": "price",
                "text": "Ab welchem Preis wäre das Produkt so billig, dass du an der Qualität zweifelst?",
            },
            {
                "id": "cheap_acceptable",
                "type": "price",
                "text": "Ab welchem Preis findest du das Produkt günstig (gutes Angebot)?",
            },
            {
                "id": "expensive_acceptable",
                "type": "price",
                "text": "Ab welchem Preis empfindest du das Produkt als teuer (würdest aber noch kaufen)?",
            },
            {
                "id": "too_expensive",
                "type": "price",
                "text": "Ab welchem Preis wäre das Produkt so teuer, dass du es nicht mehr kaufen würdest?",
            },
        ],
    },
    "feature_priority": {
        "label": "Feature-Priorisierung",
        "description": "Welche Funktionen sind deinen Personas am wichtigsten?",
        "questions": [
            {
                "id": "must_have",
                "type": "open",
                "text": "Welche Funktion des Produkts ist für dich absolut unverzichtbar?",
            },
            {
                "id": "nice_to_have",
                "type": "open",
                "text": "Welche Funktion wäre ein angenehmes Extra, auf das du aber verzichten könntest?",
            },
            {
                "id": "missing",
                "type": "open",
                "text": "Welche Funktion fehlt dir, die du gerne hättest?",
            },
            {
                "id": "remove",
                "type": "open",
                "text": "Welche Funktion würdest du entfernen oder vereinfachen?",
            },
        ],
    },
}


# ── Response & result models ──────────────────────────────────────────────────

@dataclass
class PersonaResponse:
    persona_id: str
    persona_display: str
    persona_traits: list[str]
    persona_age: int
    persona_region: str
    answers: dict[str, Any]   # {question_id: value}


@dataclass
class AggregatedInsight:
    question_id: str
    question_text: str
    question_type: QuestionType
    # For scale questions
    avg_score: float | None = None
    score_distribution: dict[int, int] | None = None
    # For choice questions
    choice_counts: dict[str, int] | None = None
    # For price questions
    avg_price: float | None = None
    price_percentiles: dict[str, float] | None = None
    # For open questions
    themes: list[str] | None = None      # extracted by Claude
    sample_quotes: list[str] | None = None
    claude_summary: str = ""


@dataclass
class ResearchReport:
    template_name: str
    product_description: str
    persona_count: int
    responses: list[PersonaResponse] = field(default_factory=list)
    insights: list[AggregatedInsight] = field(default_factory=list)
    executive_summary: str = ""

    def to_markdown(self) -> str:
        lines = [
            "# Synthetic Consumer Panel — Forschungsbericht",
            f"**Konzept:** {self.product_description[:200]}",
            f"**Methode:** {self.template_name}",
            f"**Panel-Größe:** {self.persona_count} Personas",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
            self.executive_summary,
            "",
            "---",
            "",
            "## Detailergebnisse",
            "",
        ]
        for ins in self.insights:
            lines += [f"### {ins.question_text}", ""]
            if ins.avg_score is not None:
                lines.append(f"**Ø Score:** {ins.avg_score:.1f}/10")
            if ins.avg_price is not None:
                lines.append(f"**Ø Preis:** {ins.avg_price:.2f} EUR")
            if ins.choice_counts:
                for opt, cnt in sorted(ins.choice_counts.items(), key=lambda x: -x[1]):
                    pct = cnt / self.persona_count * 100
                    lines.append(f"- {opt}: {cnt} ({pct:.0f}%)")
            if ins.claude_summary:
                lines += ["", ins.claude_summary]
            if ins.sample_quotes:
                lines += ["", "**Stimmen aus dem Panel:**"]
                for q in ins.sample_quotes[:5]:
                    lines.append(f'> "{q}"')
            lines += ["", ""]
        return "\n".join(lines)
