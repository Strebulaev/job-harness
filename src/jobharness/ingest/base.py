"""Source adapter protocol + RawJob (spec §11.1).

Every ingest adapter implements :class:`SourceAdapter` and yields
:class:`RawJob` items. The pipeline wraps each adapter with rate-limiting,
``User-Agent``, ``robots.txt`` checks, and ETag/If-Modified-Since caching
(spec §11.1, §2.4).

Adapters declare ``tos_notes`` and ``allowed_actions`` in code; the
pipeline refuses to call an action not in ``allowed_actions``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

FetchAction = Literal["fetch", "send"]


@dataclass(slots=True)
class RawJob:
    """One job posting as returned by an adapter, before dedup/normalization."""

    source: str
    external_id: str
    url: str
    title: str
    company: str | None
    jd_text: str
    posted_at: datetime | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SourceAdapter(Protocol):
    """Async source adapter. ``fetch`` yields :class:`RawJob` items."""

    name: str
    tos_notes: str
    allowed_actions: set[FetchAction]

    async def fetch(
        self, since: datetime | None = None
    ) -> AsyncIterator[RawJob]: ...


__all__ = [
    "FetchAction",
    "RawJob",
    "SourceAdapter",
]
