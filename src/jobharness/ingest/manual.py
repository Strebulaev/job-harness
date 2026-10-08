"""Manual ingest adapter (spec §11.1).

The Principal pastes a URL or JD text via the CLI (``jh job add --url …
[--paste]``). This adapter wraps the pasted content in a
:class:`~jobharness.ingest.base.RawJob` so it flows through the same
dedup + insert path as every other source.

ToS: n/a — user-initiated, no programmatic access to a third-party
platform.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal

from jobharness.ingest.base import RawJob


class ManualAdapter:
    """Wraps a single pasted URL/JD into a :class:`RawJob`."""

    name: str = "manual"
    tos_notes: str = "n/a — user-initiated; no programmatic access."
    allowed_actions: set[Literal["fetch", "send"]] = {"fetch"}

    async def fetch(
        self, since: datetime | None = None
    ) -> AsyncIterator[RawJob]:
        raise NotImplementedError(
            "ManualAdapter.fetch is a no-op; use jh job add to insert a "
            "pasted URL/JD directly."
        )

    def make_raw(
        self,
        *,
        url: str,
        jd_text: str,
        title: str | None = None,
        company: str | None = None,
        external_id: str | None = None,
    ) -> RawJob:
        """Build a :class:`RawJob` from a pasted URL + JD text."""
        return RawJob(
            source=self.name,
            external_id=external_id or "manual",
            url=url,
            title=title or url,
            company=company,
            jd_text=jd_text,
        )


__all__ = ["ManualAdapter"]
