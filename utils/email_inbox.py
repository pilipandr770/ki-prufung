"""
IMAP catch-all inbox reader for AI persona email verification.

All test personas receive addresses like  test-{id8}@andrii-it.de.
All those mails land in the catch-all inbox at  info@andrii-it.de.
We connect via IMAP, search by the exact TO address, extract any
verification URL from the body, then mark the message as deleted.
"""
from __future__ import annotations

import imaplib
import email
import re
import time
from email.header import decode_header
from typing import Optional

from config import settings


def _decode_str(raw: bytes | str, charset: str | None = "utf-8") -> str:
    if isinstance(raw, str):
        return raw
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except (LookupError, UnicodeDecodeError):
        return raw.decode("latin-1", errors="replace")


def _extract_urls(text: str) -> list[str]:
    """Return all http(s) URLs found in *text*."""
    return re.findall(r"https?://[^\s\"'<>]+", text)


def _get_plain_text(msg: email.message.Message) -> str:
    """Extract plain-text content from a (possibly multipart) message."""
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset()
                if payload:
                    parts.append(_decode_str(payload, charset))
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset()
        if payload:
            parts.append(_decode_str(payload, charset))
    return "\n".join(parts)


def _connect() -> imaplib.IMAP4_SSL | imaplib.IMAP4:
    if settings.imap_use_ssl:
        conn = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
    else:
        conn = imaplib.IMAP4(settings.imap_host, settings.imap_port)
    conn.login(settings.imap_user, settings.imap_password)
    return conn


def wait_for_verification_link(
    persona_email: str,
    *,
    timeout_s: int | None = None,
    poll_interval_s: int = 6,
) -> Optional[str]:
    """
    Block until a verification e-mail arrives for *persona_email* or
    *timeout_s* seconds elapse.  Returns the first URL found in the
    message, or ``None`` on timeout.

    Parameters
    ----------
    persona_email:
        The recipient address, e.g. ``test-a1b2c3d4@andrii-it.de``.
    timeout_s:
        How long to wait.  Defaults to ``settings.email_wait_timeout_s``.
    poll_interval_s:
        How often to re-check the inbox while waiting.
    """
    if not settings.imap_configured:
        raise RuntimeError(
            "IMAP not configured — set IMAP_HOST and IMAP_PASSWORD in .env"
        )

    deadline = time.monotonic() + (timeout_s or settings.email_wait_timeout_s)

    while time.monotonic() < deadline:
        url = _check_inbox_for(persona_email)
        if url:
            return url
        remaining = deadline - time.monotonic()
        time.sleep(min(poll_interval_s, max(0, remaining)))

    return None


def _check_inbox_for(persona_email: str) -> Optional[str]:
    """
    Open the catch-all inbox once, search for a mail addressed to
    *persona_email*, extract the first URL, and expunge the message.
    Returns ``None`` if no matching mail was found yet.
    """
    try:
        conn = _connect()
        conn.select("INBOX")

        # Search by exact TO header value
        _, data = conn.search(None, f'TO "{persona_email}"')
        uids = data[0].split() if data and data[0] else []
        if not uids:
            conn.logout()
            return None

        # Use the most recent matching message
        uid = uids[-1]
        _, msg_data = conn.fetch(uid, "(RFC822)")
        raw = msg_data[0][1] if msg_data and msg_data[0] else None
        if raw is None:
            conn.logout()
            return None

        msg = email.message_from_bytes(raw)
        text = _get_plain_text(msg)
        urls = _extract_urls(text)

        # Mark as deleted so it doesn't show up in future searches
        conn.store(uid, "+FLAGS", "\\Deleted")
        conn.expunge()
        conn.logout()

        return urls[0] if urls else None

    except Exception:
        # Don't crash the caller — return None and let the polling loop retry
        return None


def list_persona_emails(persona_emails: list[str]) -> dict[str, list[str]]:
    """
    One-shot check: return a dict mapping each address in *persona_emails*
    to the list of URLs found in any matching inbox messages.
    Useful for diagnostics / the UI "check status" button.
    Consumed messages are expunged.
    """
    if not settings.imap_configured:
        return {}

    results: dict[str, list[str]] = {e: [] for e in persona_emails}
    try:
        conn = _connect()
        conn.select("INBOX")
        for addr in persona_emails:
            _, data = conn.search(None, f'TO "{addr}"')
            uids = data[0].split() if data and data[0] else []
            for uid in uids:
                _, msg_data = conn.fetch(uid, "(RFC822)")
                raw = msg_data[0][1] if msg_data and msg_data[0] else None
                if raw:
                    msg = email.message_from_bytes(raw)
                    urls = _extract_urls(_get_plain_text(msg))
                    results[addr].extend(urls)
                conn.store(uid, "+FLAGS", "\\Deleted")
            conn.expunge()
        conn.logout()
    except Exception:
        pass
    return results
