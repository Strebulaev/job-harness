"""RSS/Atom ingest adapter (spec §11.1).

Fetches a config-driven list of RSS/Atom feed URLs and yields one
:class:`~jobharness.ingest.base.RawJob` per item. Each feed URL is
treated as a source; the adapter identifies itself via ``User-Agent``
and honors ``ETag``/``If-Modified-Since`` caching (spec §11.1).

The feed list comes from ``config.ingest.rss_feeds`` (a list of URLs).
Adding a feed is a config change, not a code change.

ToS: varies by feed; each feed's ToS is recorded in ``docs/SOURCES.md``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal
from xml.etree import ElementTree

import httpx

from jobharness.ingest.base import RawJob

_RSS_ITEM_TAGS = (
    "{http://www.w3.org/2005/Atom}entry",
    "{http://purl.org/rss/1.0/}item",
    "item",
    "entry",
)


def _text(elem: ElementTree.Element, *tags: str) -> str | None:
    for t in tags:
        child = elem.find(t)
        if child is not None and child.text:
            return child.text.strip()
    return None


def _parse_feed(xml_text: str) -> list[dict[str, Any]]:
    """Parse RSS 2.0 / Atom XML into a list of item dicts."""
    root = ElementTree.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    for item in root.iter():
        if item.tag not in _RSS_ITEM_TAGS:
            continue
        title = _text(item, "title")
        link_el = item.find("link")
        link = None
        if link_el is not None:
            link = link_el.text.strip() if link_el.text else link_el.get("href")
        desc_el = item.find("description")
        description = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
        content_el = item.find(
            "{http://purl.org/rss/1.0/}description"
        ) or item.find("content")
        content = (
            content_el.text.strip()
            if content_el is not None and content_el.text
            else ""
        )
        pub_el = item.find("pubDate") or item.find(
            "{http://purl.org/rss/1.0/}updated"
        ) or item.find("{http://www.w3.org/2005/Atom}updated")
        published = pub_el.text.strip() if pub_el is not None and pub_el.text else None
        items.append(
            {
                "title": title or "",
                "link": link or "",
                "description": description,
                "content": content,
                "published": published,
            }
        )
    return items


class RssAdapter:
    """Fetches a list of RSS/Atom feeds and yields :class:`RawJob` items."""

    name: str = "rss"
    tos_notes: str = (
        "Varies by feed; each feed's ToS is recorded in docs/SOURCES.md. "
        "The adapter identifies itself via User-Agent and honors "
        "ETag/If-Modified-Since."
    )
    allowed_actions: set[Literal["fetch", "send"]] = {"fetch"}

    def __init__(
        self,
        feed_urls: list[str],
        *,
        user_agent: str = "jobharness/0.1",
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._transport = transport
        self._feeds = list(feed_urls)
        self._ua = user_agent
        self._timeout = timeout
        self._cache: dict[str, dict[str, str | None]] = {}

    def _cache_get(self, url: str) -> dict[str, str | None]:
        return self._cache.get(url, {"etag": None, "last_modified": None})

    def _cache_set(self, url: str, etag: str | None, last_modified: str | None) -> None:
        self._cache[url] = {"etag": etag, "last_modified": last_modified}

    async def fetch(
        self, since: datetime | None = None
    ) -> AsyncIterator[RawJob]:
        """Yield one :class:`RawJob` per feed item."""
        headers: dict[str, str] = {"User-Agent": self._ua}
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            for feed_url in self._feeds:
                cached = self._cache_get(feed_url)
                etag = cached.get("etag")
                if etag:
                    headers["If-None-Match"] = etag
                lm = cached.get("last_modified")
                if lm:
                    headers["If-Modified-Since"] = lm
                try:
                    resp = await client.get(feed_url, headers=headers)
                except httpx.HTTPError as e:
                    raise RuntimeError(f"RSS fetch failed for {feed_url}: {e}") from e
                if resp.status_code == 304:
                    continue
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"RSS fetch returned {resp.status_code} for {feed_url}"
                    )
                self._cache_set(
                    feed_url,
                    resp.headers.get("ETag"),
                    resp.headers.get("Last-Modified"),
                )
                items = _parse_feed(resp.text)
                for i, item in enumerate(items):
                    link = item["link"] or feed_url
                    jd_text = item["content"] or item["description"]
                    if not jd_text:
                        continue
                    yield RawJob(
                        source=self.name,
                        external_id=f"{feed_url}#{i}",
                        url=link,
                        title=item["title"] or link,
                        company=None,
                        jd_text=jd_text,
                        posted_at=None,
                    )


__all__ = ["RssAdapter"]
