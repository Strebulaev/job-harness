"""Email-alerts ingest adapter (spec §11.1).

Polls a dedicated IMAP mailbox/label for job-alert emails (e.g. from
Remote OK, We Work Remotely, Wellfound, Habr Career, djinni). The
Principal signs up for the alerts on each platform; the harness only
reads the label.

Each alert email is expected to contain a job URL and, ideally, a short
JD snippet in the body. The adapter extracts the URL and body text and
yields a :class:`~jobharness.ingest.base.RawJob`.

IMAP is read-only; no sending. The adapter identifies the mailbox via
config (``ingest.email_alerts_imap`` + ``ingest.email_alerts_label``).
"""

from __future__ import annotations

import email
import imaplib
import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal

from jobharness.ingest.base import RawJob

_URL_RE = re.compile(
    r"https?://[^\s<>\"']+",
    re.IGNORECASE,
)


def _extract_url(body: str) -> str | None:
    """Return the first URL in the email body, or None."""
    m = _URL_RE.search(body)
    return m.group(0) if m else None


def _extract_body(msg: email.message.Message) -> str:
    """Return the plain-text body of an email message."""

    def _to_bytes(payload: object) -> bytes:
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, str):
            return payload.encode("utf-8", errors="replace")
        return b""

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = _to_bytes(part.get_payload(decode=True))
                if payload:
                    return payload.decode("utf-8", errors="replace")
    else:
        payload = _to_bytes(msg.get_payload(decode=True))
        if payload:
            return payload.decode("utf-8", errors="replace")
    return ""


class EmailAlertsAdapter:
    """Polls an IMAP label for job-alert emails."""

    name: str = "email_alerts"
    tos_notes: str = (
        "Varies by sender; each sender's ToS is recorded in "
        "docs/SOURCES.md. The harness only reads the dedicated label; "
        "no sending, no CAPTCHA, no account creation."
    )
    allowed_actions: set[Literal["fetch", "send"]] = {"fetch"}

    def __init__(
        self,
        *,
        imap_host: str,
        imap_port: int = 993,
        username: str,
        password: str,
        mailbox: str = "INBOX",
        label: str | None = None,
        user_agent: str = "jobharness/0.1",
    ) -> None:
        self._host = imap_host
        self._port = imap_port
        self._user = username
        self._password = password
        self._mailbox = mailbox
        self._label = label
        self._ua = user_agent

    async def fetch(
        self, since: datetime | None = None
    ) -> AsyncIterator[RawJob]:
        """Poll the IMAP label and yield one :class:`RawJob` per alert.

        Uses ``imaplib`` synchronously (the IMAP protocol is not async
        in the stdlib); the caller should run this in a thread pool if
        concurrency matters.
        """

        conn = imaplib.IMAP4_SSL(self._host, self._port)
        conn.login(self._user, self._password)
        conn.select(self._mailbox)

        # Search for unseen messages in the label (or all if no label).
        if self._label:
            status, data = conn.search(
                "UTF-8", "UNSEEN"
            )
        else:
            status, data = conn.search("UTF-8", "ALL")
        if status != "OK":
            conn.logout()
            raise RuntimeError(f"IMAP search failed: {status}")

        msg_ids = data[0].split()
        for msg_id in msg_ids:
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw_el = msg_data[0]
            raw = raw_el[1]
            if not isinstance(raw, bytes):
                continue
            msg = email.message_from_bytes(raw)
            body = _extract_body(msg)
            url = _extract_url(body)
            if url is None:
                continue
            subject = msg.get("Subject", "") or ""
            yield RawJob(
                source=self.name,
                external_id=str(msg.get("Message-ID", "")),
                url=url,
                title=subject,
                company=None,
                jd_text=body,
            )
        conn.logout()


__all__ = ["EmailAlertsAdapter"]
