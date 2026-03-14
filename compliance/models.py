"""Data models for EU/DE compliance reports."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class LegalIssue:
    severity: Severity
    category: str
    issue: str
    recommendation: str


@dataclass
class PageCheck:
    name: str           # "Impressum", "Datenschutzerklärung", etc.
    law_basis: str      # "§5 TMG", "DSGVO Art. 13", etc.
    url: str            # URL where it was found, or ""
    found: bool
    issues: list[LegalIssue] = field(default_factory=list)
    content_ok: bool = False
    content_excerpt: str = ""
    claude_analysis: str = ""

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)


@dataclass
class CookieBannerCheck:
    present: bool
    reject_option: bool       # Can the user reject non-essential cookies?
    pre_checked_boxes: bool   # Pre-checked consent boxes (illegal under DSGVO)
    screenshot_b64: str = ""
    claude_analysis: str = ""
    issues: list[LegalIssue] = field(default_factory=list)


@dataclass
class ComplianceReport:
    target_url: str
    page_checks: list[PageCheck]
    cookie_check: CookieBannerCheck | None
    score: int     # 0–100
    grade: str     # A / B / C / D / F
    summary: str
    critical_count: int
    warning_count: int

    def to_markdown(self) -> str:
        lines = [
            f"# EU/DE Compliance Report",
            f"**URL:** {self.target_url}",
            f"**Score:** {self.score}/100 — Note **{self.grade}**",
            "",
            self.summary,
            "",
            "---",
            "",
        ]

        # Cookie banner
        if self.cookie_check:
            cb = self.cookie_check
            status = "✅" if cb.present and cb.reject_option and not cb.pre_checked_boxes else "⚠️"
            lines += [
                f"## {status} Cookie-Consent-Banner (TTDSG / DSGVO)",
                f"- Banner vorhanden: {'✅' if cb.present else '❌'}",
                f"- Ablehnen möglich: {'✅' if cb.reject_option else '❌'}",
                f"- Vorausgewählte Checkboxen: {'🔴 JA (DSGVO-Verstoß!)' if cb.pre_checked_boxes else '✅ Nein'}",
                "",
                cb.claude_analysis,
                "",
            ]
            for iss in cb.issues:
                icon = "🔴" if iss.severity == Severity.CRITICAL else "🟡"
                lines += [f"{icon} **{iss.issue}**  ", f"  → {iss.recommendation}", ""]

        # Page checks
        for pc in self.page_checks:
            if not pc.found:
                icon = "❌"
            elif pc.critical_count > 0:
                icon = "🔴"
            elif pc.warning_count > 0:
                icon = "🟡"
            else:
                icon = "✅"

            lines += [
                f"## {icon} {pc.name} ({pc.law_basis})",
                f"**URL:** {pc.url or 'nicht gefunden'}",
                "",
            ]
            if pc.claude_analysis:
                lines += [pc.claude_analysis, ""]
            for iss in pc.issues:
                sev_icon = "🔴" if iss.severity == Severity.CRITICAL else "🟡"
                lines += [f"{sev_icon} **{iss.issue}**  ", f"  → {iss.recommendation}", ""]
            lines.append("---")
            lines.append("")

        return "\n".join(lines)
