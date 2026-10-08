"""M2-2 tests: RSS adapter against a local fixture feed.

Uses httpx's MockTransport to serve a local RSS XML fixture, so the
test runs offline (spec §12: the whole suite MUST run offline).

The adapter's ``fetch`` creates its own ``httpx.AsyncClient``; to test
it offline we use a ``httpx.MockTransport`` patched via
``httpx.AsyncClient``'s constructor. Since the adapter owns the client,
we test the parse path directly and verify the adapter's public
interface (name, tos_notes, allowed_actions, feed list).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from jobharness.ingest.base import RawJob
from jobharness.ingest.rss import RssAdapter, _parse_feed

REPO_ROOT = Path(__file__).resolve().parents[2]
FEED_XML = REPO_ROOT / "tests" / "fixtures" / "rss" / "test_feed.xml"
FEED_URL = "https://example.com/jobs/feed.xml"


def test_parse_feed_extracts_items():
    xml = FEED_XML.read_text(encoding="utf-8")
    items = _parse_feed(xml)
    assert len(items) == 3
    assert items[0]["title"] == "Senior Backend Engineer (Contract)"
    assert items[0]["link"] == "https://example.com/jobs/101"
    assert "Python" in items[0]["description"]
    assert items[1]["title"] == "AI/LLM Engineer (B2B)"
    assert items[2]["title"] == "Junior Developer (Employment)"


def test_parse_feed_empty():
    items = _parse_feed("<rss version='2.0'><channel></channel></rss>")
    assert items == []


def test_parse_feed_invalid_xml():
    from xml.etree import ElementTree

    with pytest.raises(ElementTree.ParseError):
        _parse_feed("not xml at all")


def test_rss_adapter_interface():
    """The adapter declares the required SourceAdapter fields."""
    adapter = RssAdapter(feed_urls=[FEED_URL])
    assert adapter.name == "rss"
    assert "fetch" in adapter.allowed_actions
    assert "send" not in adapter.allowed_actions
    assert adapter.tos_notes


def test_rss_adapter_fetch_uses_mock_transport(monkeypatch):
    """Patch httpx.AsyncClient to use a MockTransport, then fetch."""
    xml = FEED_XML.read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/jobs/feed.xml":
            return httpx.Response(
                200, content=xml, headers={"Content-Type": "application/rss+xml"}
            )
        return httpx.Response(404)

    real_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        kwargs.pop("base_url", None)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    adapter = RssAdapter(feed_urls=[FEED_URL])
    raw_jobs = []
    import asyncio

    async def _collect() -> list[RawJob]:
        out: list[RawJob] = []
        async for raw in adapter.fetch():
            out.append(raw)
        return out

    raw_jobs = asyncio.run(_collect())
    assert len(raw_jobs) == 3
    assert raw_jobs[0].url == "https://example.com/jobs/101"
    assert raw_jobs[0].title == "Senior Backend Engineer (Contract)"
    assert raw_jobs[0].source == "rss"
    assert "Python" in raw_jobs[0].jd_text
    assert raw_jobs[1].url == "https://example.com/jobs/102"
    assert raw_jobs[2].url == "https://example.com/jobs/103"
