"""Data models for the AI UX testing engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Outcome of a single test step for one persona."""
    step_index: int
    step_description: str
    status: StepStatus = StepStatus.PENDING
    # Base-64 encoded PNG screenshot taken after the step
    screenshot_b64: str = ""
    # Short HTML snippet around the interacted element (for Claude context)
    html_snippet: str = ""
    # Claude Vision's natural-language analysis of the step
    claude_analysis: str = ""
    # Was a DSGVO / privacy issue flagged?
    dsgvo_flag: bool = False
    # Raw error message if status == FAILED
    error: str = ""


@dataclass
class PersonaTestRun:
    """All step results for one persona executing a scenario."""
    persona_id: str
    persona_display: str
    persona_email: str
    results: list[StepResult] = field(default_factory=list)
    # Final overall verdict from Claude
    overall_verdict: str = ""
    # Was registration successful?
    registered: bool = False
    # Was the account deleted at the end?
    deleted: bool = False

    @property
    def passed_steps(self) -> int:
        return sum(1 for r in self.results if r.status == StepStatus.PASSED)

    @property
    def failed_steps(self) -> int:
        return sum(1 for r in self.results if r.status == StepStatus.FAILED)

    @property
    def dsgvo_issues(self) -> list[StepResult]:
        return [r for r in self.results if r.dsgvo_flag]


@dataclass
class TestScenario:
    """
    Defines what the AI personas should do on the target website.

    Steps are plain-language descriptions of actions, e.g.:
      1. "Register a new account using the provided email and password"
      2. "Confirm the registration via the verification email link"
      3. "Log in with the registered credentials"
      4. "Navigate to the profile / settings page"
      5. "Delete the account"
    """
    target_url: str
    steps: list[str]
    # If True, the runner attempts to delete the account as the final step
    # even if it's not explicitly listed in steps
    auto_delete: bool = True
    # Language hint for Claude prompts
    language: str = "de"


@dataclass
class TestSession:
    """Top-level container for a full multi-persona test run."""
    scenario: TestScenario
    persona_runs: list[PersonaTestRun] = field(default_factory=list)
    summary: str = ""

    @property
    def total_personas(self) -> int:
        return len(self.persona_runs)

    @property
    def successful_registrations(self) -> int:
        return sum(1 for r in self.persona_runs if r.registered)

    @property
    def successful_deletions(self) -> int:
        return sum(1 for r in self.persona_runs if r.deleted)

    @property
    def all_dsgvo_issues(self) -> list[tuple[str, StepResult]]:
        issues = []
        for run in self.persona_runs:
            for step in run.dsgvo_issues:
                issues.append((run.persona_display, step))
        return issues
