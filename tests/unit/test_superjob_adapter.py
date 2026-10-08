"""Step 3.3: SuperJob adapter on the assumed (unverified) API shape."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from jobharness.ingest.superjob import (
    SuperJobAdapter,
    SuperJobAuthError,
    SuperJobError,
    build_superjob_queries,
    vacancy_to_rawjob,
)
from jobharness.schemas.profile import load_profile

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = json.loads((ROOT / "tests" / "fixtures" / "superjob" / "vacancies_sample.json").read_text())


async def _nosleep(_: float) -> None:
    return None


def _adapter(handler, queries=None, **kw):  # type: ignore[no-untyped-def]
    return SuperJobAdapter(
        lambda: "KEY", queries or [{"keyword": "python"}],
        transport=httpx.MockTransport(handler), sleep=_nosleep, **kw,
    )


async def _collect(adapter: SuperJobAdapter, since=None):  # type: ignore[no-untyped-def]
    return [r async for r in adapter.fetch(since)]


def test_field_mapping_and_payment_text() -> None:
    raw = vacancy_to_rawjob(SAMPLE["objects"][0])
    assert raw.source == "superjob" and raw.external_id == "900001"
    assert raw.company == "Acme Logistics" and raw.url.endswith("900001.html")
    assert "Payment: 150000-220000 RUB per month" in raw.jd_text
    assert "FastAPI" in raw.jd_text and "<p>" not in raw.jd_text
    assert raw.posted_at is not None and raw.posted_at.tzinfo is not None


def test_missing_payment_has_no_payment_line() -> None:
    raw = vacancy_to_rawjob(SAMPLE["objects"][1])
    assert "Payment" not in raw.jd_text
    assert "ETL" in raw.jd_text  # falls back to work/candidat when no rich text


async def test_fetch_sends_key_header_and_paginates() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        page = int(req.url.params["page"])
        objs = [SAMPLE["objects"][page]]
        return httpx.Response(200, json={"objects": objs, "total": 2, "more": page == 0})

    jobs = await _collect(_adapter(handler, per_page=1))
    assert [j.external_id for j in jobs] == ["900001", "900002"]
    assert all(r.headers["X-Api-App-Id"] == "KEY" for r in seen)
    assert [r.url.params["page"] for r in seen] == ["0", "1"]


async def test_duplicates_across_queries_are_dropped() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"objects": SAMPLE["objects"], "more": False})

    jobs = await _collect(_adapter(handler, [{"keyword": "a"}, {"keyword": "b"}]))
    assert len(jobs) == 2


async def test_since_filters_old_postings() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"objects": SAMPLE["objects"], "more": False})

    cutoff = datetime.fromtimestamp(1759850000, UTC)
    jobs = await _collect(_adapter(handler), since=cutoff)
    assert [j.external_id for j in jobs] == ["900001"]


async def test_401_and_429() -> None:
    with pytest.raises(SuperJobAuthError) as ei:
        await _collect(_adapter(lambda r: httpx.Response(401)))
    assert "KEY" not in str(ei.value)
    with pytest.raises(SuperJobError, match="rate limited"):
        await _collect(_adapter(lambda r: httpx.Response(429)))
    assert await _adapter(lambda r: httpx.Response(401)).check_key() is False
    ok = _adapter(lambda r: httpx.Response(200, json={"objects": [], "more": False}))
    assert await ok.check_key() is True


def test_queries_from_profile() -> None:
    profile = load_profile(str(ROOT / "config" / "profile.example.yaml"))
    qs = build_superjob_queries(profile)
    keywords = [q["keyword"] for q in qs]
    assert keywords[:2] == ["Python", "SQL"]  # expert skills first
    assert "CTO" in keywords or "Staff Engineer" in keywords
    assert len(keywords) <= 4
