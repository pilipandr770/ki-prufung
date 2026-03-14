"""
Playwright-based interaction runner for AI persona testing.

Each step in a TestScenario is executed with a real browser session.
The runner:
  1. Navigates to the target URL
  2. For each step, asks Claude what to do (action JSON)
  3. Executes the action (fill, click, navigate, wait)
  4. Takes a screenshot + grabs relevant HTML
  5. Optionally polls the IMAP inbox for email verification links
  6. Returns the populated StepResult list for one persona
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
from typing import Optional

import anthropic
from playwright.async_api import Page

from config import settings
from personas.models import Persona
from utils.email_inbox import wait_for_verification_link
from .models import TestScenario, StepResult, StepStatus, PersonaTestRun

# ─── Claude action planner ──────────────────────────────────────────────────

_ACTION_SYSTEM = """You are a browser automation assistant.
Given a screenshot of a webpage plus a goal, return ONLY a JSON action object.
Possible actions:
  {"action": "fill",   "selector": "CSS_SELECTOR", "value": "TEXT"}
  {"action": "click",  "selector": "CSS_SELECTOR"}
  {"action": "navigate","url": "FULL_URL"}
  {"action": "wait",   "ms": 2000}
  {"action": "done"}   // step is already complete or cannot be completed

Prefer visible, semantic selectors (input[type=email], button[type=submit], etc.).
Never use XPath. Return only the JSON, no other text."""


async def _ask_claude_for_action(
    page: Page,
    step_description: str,
    persona: Persona,
    extra_context: str = "",
) -> dict:
    """Screenshot current page and ask Claude what single action to perform next."""
    screenshot_bytes = await page.screenshot(full_page=False, type="png")
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

    b2b_info = f"\nFirma: {persona.b2b_context}" if persona.b2b_context else ""
    user_text = (
        f"Persona: {persona.display_name} (email: {persona.email}, password: {persona.password}){b2b_info}\n"
        f"Goal: {step_description}\n"
        f"{('Context: ' + extra_context) if extra_context else ''}\n\n"
        "What single browser action should be performed next?"
    )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=200,
            system=_ACTION_SYSTEM,
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
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        )
        raw = response.content[0].text
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return {"action": "done"}


async def _execute_action(page: Page, action: dict) -> None:
    """Execute a single action dict on *page*."""
    act = action.get("action", "done")
    if act == "fill":
        await page.fill(action["selector"], action.get("value", ""))
    elif act == "click":
        await page.click(action["selector"])
    elif act == "navigate":
        await page.goto(action["url"], wait_until="domcontentloaded", timeout=30_000)
    elif act == "wait":
        await asyncio.sleep(action.get("ms", 1000) / 1000)
    # "done" → no-op


async def _take_screenshot_b64(page: Page) -> str:
    buf = await page.screenshot(full_page=False, type="png")
    return base64.b64encode(buf).decode()


async def _get_html_snippet(page: Page, max_chars: int = 3000) -> str:
    try:
        html = await page.content()
        # Strip scripts/styles to reduce noise
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        return html[:max_chars]
    except Exception:
        return ""


# ─── Step executor ──────────────────────────────────────────────────────────

async def _run_step(
    page: Page,
    step_index: int,
    step_description: str,
    persona: Persona,
    verification_email: Optional[str] = None,
) -> StepResult:
    """
    Run Claude in a planning loop (up to 8 actions) until the step is done
    or we hit the action limit.  Returns a populated StepResult.
    """
    result = StepResult(
        step_index=step_index,
        step_description=step_description,
        status=StepStatus.RUNNING,
    )

    is_email_step = any(
        kw in step_description.lower()
        for kw in ("verif", "confirm", "bestätig", "email", "e-mail", "link")
    )

    extra_context = ""
    if is_email_step and settings.imap_configured:
        # Block and wait for the verification link in a thread pool
        # (IMAP is synchronous; we run it off the event loop)
        loop = asyncio.get_event_loop()
        link = await loop.run_in_executor(
            None,
            lambda: wait_for_verification_link(
                verification_email or persona.email, timeout_s=settings.email_wait_timeout_s
            ),
        )
        if link:
            await page.goto(link, wait_until="domcontentloaded", timeout=30_000)
            extra_context = f"Navigated to verification link: {link}"
        else:
            extra_context = "No verification email received within timeout."

    max_actions = 8
    for _ in range(max_actions):
        action = await _ask_claude_for_action(page, step_description, persona, extra_context)
        if action.get("action") == "done":
            break
        try:
            await _execute_action(page, action)
            await page.wait_for_load_state("domcontentloaded", timeout=15_000)
        except Exception as exc:
            result.error = str(exc)
            break

    result.screenshot_b64 = await _take_screenshot_b64(page)
    result.html_snippet = await _get_html_snippet(page)
    # Status will be updated by evaluator.py after Claude Vision analysis
    result.status = StepStatus.PENDING
    return result


# ─── Delete-account helper ───────────────────────────────────────────────────

_DELETE_SYSTEM = """You are a browser automation assistant.
Look at the screenshot and return ONLY a JSON object with the CSS selector
of the delete-account button/link, or null if not visible.
Format: {"selector": "CSS_SELECTOR_OR_NULL"}"""


async def find_and_click_delete_button(page: Page) -> bool:
    """
    Ask Claude to locate the delete-account control and click it.
    Tries up to 3 confirmation dialogs automatically.
    Returns True if a selector was found and clicked.
    """
    screenshot_bytes = await page.screenshot(full_page=True, type="png")
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=100,
            system=_DELETE_SYSTEM,
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
                        {"type": "text", "text": "Find the delete account button or link."},
                    ],
                }
            ],
        )
        raw = response.content[0].text
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return False
        data = json.loads(m.group())
        selector = data.get("selector")
        if not selector or selector == "null":
            return False
    except Exception:
        return False

    try:
        await page.click(selector, timeout=5_000)
        # Handle up to 3 confirmation dialogs / "confirm" buttons
        for _ in range(3):
            await asyncio.sleep(1)
            for confirm_sel in [
                "button[type=submit]",
                "button:has-text('Bestätigen')",
                "button:has-text('Confirm')",
                "button:has-text('Ja')",
                "button:has-text('Yes')",
                "button:has-text('Delete')",
                "button:has-text('Löschen')",
            ]:
                try:
                    btn = page.locator(confirm_sel).first
                    if await btn.is_visible(timeout=1_000):
                        await btn.click()
                        break
                except Exception:
                    continue
        return True
    except Exception:
        return False


# ─── Main persona runner ─────────────────────────────────────────────────────

async def run_persona_test(
    persona: Persona,
    scenario: TestScenario,
    *,
    headless: bool = True,
) -> PersonaTestRun:
    """
    Execute *scenario* for a single *persona* using a fresh browser context.
    Evaluator calls are made by the caller (testing/engine.py) to keep this
    module focused on browser interaction only.
    """
    run = PersonaTestRun(
        persona_id=persona.id,
        persona_display=persona.display_name,
        persona_email=persona.email,
    )

    from scraper.browser import launch_stealth_browser, close_browser  # local import avoids circular deps

    pw, browser, context = await launch_stealth_browser(headless=headless, language=persona.language)
    page = await context.new_page()

    try:
        await page.goto(
            scenario.target_url, wait_until="domcontentloaded", timeout=30_000
        )

        for idx, step_desc in enumerate(scenario.steps):
            step_result = await _run_step(
                page, idx, step_desc, persona, persona.email
            )
            run.results.append(step_result)

            # Mark registration done after the first step roughly matching "register"
            if not run.registered and any(
                kw in step_desc.lower() for kw in ("register", "sign up", "registrier", "anmeld")
            ):
                run.registered = True

        # Auto-delete step
        if scenario.auto_delete:
            deleted = await find_and_click_delete_button(page)
            run.deleted = deleted

    except Exception as exc:
        run.results.append(
            StepResult(
                step_index=len(run.results),
                step_description="[runner crashed]",
                status=StepStatus.FAILED,
                error=str(exc),
            )
        )
    finally:
        await close_browser(pw, browser)

    return run
