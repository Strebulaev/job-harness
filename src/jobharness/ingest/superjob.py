"""SuperJob API ingest adapter (decision 0014, plan step 3.3).

UNVERIFIED API SHAPE (plan step 3.2 was blocked: official docs were behind a
captcha). Assumed: ``GET https://api.superjob.ru/2.0/vacancies/`` with the
application secret key in ``X-Api-App-Id``; params ``keyword``, ``count``,
``page`` (0-based); response ``{"objects": [...], "total": N, "more": bool}``.
The key comes from an injected getter, never from settings or logs.
"""

from __future__ import annotations

import asyncio
import html
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from jobharness.ingest.base import RawJob
from jobharness.schemas.profile import Profile

BASE_URL = "https://api.superjob.ru"
VACANCIES_PATH = "/2.0/vacancies/"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_LEVEL_RANK = {"familiar": 0, "working": 1, "proficient": 2, "expert": 3}


class SuperJobError(RuntimeError):
    """A SuperJob call failed. Never contains the API key."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class SuperJobAuthError(SuperJobError):
    pass


def _clean(text: str | None) -> str:
    if not text:
        return ""
    plain = html.unescape(_TAG_RE.sub("\n", text))
    lines = [_WS_RE.sub(" ", ln).strip() for ln in plain.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def build_superjob_queries(profile: Profile, *, max_keywords: int = 3) -> list[dict[str, str]]:
    """One query per top skill (level >= working) plus the latest role title.

    Separate queries avoid an over-restrictive AND of many keywords.
    """
    skills = sorted(
        (s for s in profile.skills if _LEVEL_RANK[s.level] >= _LEVEL_RANK["working"]),
        key=lambda s: (-_LEVEL_RANK[s.level], -s.years, s.name),
    )
    keywords = [s.name for s in skills[:max_keywords]]
    if profile.experience:
        latest = max(profile.experience, key=lambda e: e.start)
        if latest.title_real not in keywords:
            keywords.append(latest.title_real)
    return [{"keyword": k} for k in keywords]


def vacancy_to_rawjob(obj: dict[str, Any]) -> RawJob:
    town = (obj.get("town") or {}).get("title")
    work_type = (obj.get("type_of_work") or {}).get("title")
    place = (obj.get("place_of_work") or {}).get("title")
    pay_from = obj.get("payment_from") or 0
    pay_to = obj.get("payment_to") or 0
    currency = str(obj.get("currency") or "").upper()
    if pay_from or pay_to:
        rng = f"{pay_from}-{pay_to}" if pay_from and pay_to else str(pay_from or pay_to)
        payment = f"Payment: {rng} {currency} per month"
    else:
        payment = ""
    body = _clean(obj.get("vacancyRichText")) or "\n".join(
        part
        for part in (
            _clean(obj.get("work")),
            _clean(obj.get("candidat")),
            _clean(obj.get("compensation")),
        )
        if part
    )
    header = [str(obj.get("profession") or "")]
    if obj.get("firm_name"):
        header.append(f"Company: {obj['firm_name']}")
    for label, value in (("Town", town), ("Type of work", work_type), ("Place of work", place)):
        if value:
            header.append(f"{label}: {value}")
    if payment:
        header.append(payment)
    jd_text = "\n".join(header + ["", body]).strip()
    published = obj.get("date_published")
    posted = datetime.fromtimestamp(int(published), UTC) if published else None
    return RawJob(
        source="superjob",
        external_id=str(obj.get("id", "")),
        url=str(obj.get("link") or ""),
        title=str(obj.get("profession") or ""),
        company=obj.get("firm_name") or None,
        jd_text=jd_text,
        posted_at=posted,
        raw_payload=obj,
    )


class SuperJobAdapter:
    name: str = "superjob"
    tos_notes: str = (
        "UNVERIFIED: terms of use not confirmed (docs captcha-blocked). "
        "Read-only vacancy search with the Principal's own application key."
    )
    allowed_actions: set[Literal["fetch", "send"]] = {"fetch"}

    def __init__(
        self,
        key_getter: Callable[[], str | None],
        queries: list[dict[str, str]],
        *,
        user_agent: str = "jobharness/0.1",
        transport: httpx.AsyncBaseTransport | None = None,
        per_page: int = 50,
        max_pages: int = 2,
        min_interval: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        timeout: float = 30.0,
    ) -> None:
        self._key_getter = key_getter
        self._queries = queries
        self._ua = user_agent
        self._transport = transport
        self._per_page = min(per_page, 100)
        self._max_pages = max_pages
        self._min_interval = min_interval
        self._sleep = sleep
        self._timeout = timeout

    async def search(self, client: httpx.AsyncClient, params: dict[str, str | int]) -> dict[str, Any]:
        key = self._key_getter()
        if not key:
            raise SuperJobAuthError("SuperJob key is not connected")
        resp = await client.get(
            VACANCIES_PATH,
            params={k: str(v) for k, v in params.items()},
            headers={"X-Api-App-Id": key, "User-Agent": self._ua},
        )
        if resp.status_code in (401, 403):
            raise SuperJobAuthError(f"key rejected ({resp.status_code})", resp.status_code)
        if resp.status_code == 429:
            raise SuperJobError("rate limited (429); try again later", 429)
        if resp.status_code >= 400:
            raise SuperJobError(f"HTTP {resp.status_code}", resp.status_code)
        data = resp.json()
        if not isinstance(data, dict):
            raise SuperJobError("unexpected response shape")
        return data

    async def check_key(self) -> bool:
        """One-result search; False when the key is rejected."""
        async with httpx.AsyncClient(
            base_url=BASE_URL, timeout=self._timeout, transport=self._transport
        ) as client:
            try:
                await self.search(client, {"keyword": "python", "count": 1, "page": 0})
            except SuperJobAuthError:
                return False
        return True

    async def fetch(self, since: datetime | None = None) -> AsyncIterator[RawJob]:
        seen: set[str] = set()
        first = True
        async with httpx.AsyncClient(
            base_url=BASE_URL, timeout=self._timeout, transport=self._transport
        ) as client:
            for query in self._queries:
                for page in range(self._max_pages):
                    if not first:
                        await self._sleep(self._min_interval)
                    first = False
                    data = await self.search(
                        client, {**query, "count": self._per_page, "page": page}
                    )
                    for obj in data.get("objects") or []:
                        raw = vacancy_to_rawjob(obj)
                        if not raw.external_id or raw.external_id in seen:
                            continue
                        seen.add(raw.external_id)
                        if since and raw.posted_at and raw.posted_at < since:
                            continue
                        yield raw
                    if not data.get("more"):
                        break


__all__ = [
    "SuperJobAdapter",
    "SuperJobAuthError",
    "SuperJobError",
    "build_superjob_queries",
    "vacancy_to_rawjob",
]
