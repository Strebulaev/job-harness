"""Step 4.6: RSS feed management."""

from __future__ import annotations

from pathlib import Path

import httpx

from jobharness.bot.testing import BotHarness, make_transport, rss_xml

URL = "https://feeds.example.com/jobs.xml"
GOOD = rss_xml([("Python contractor", "https://x.example/1", "Remote contract, Python, $3000/month.")])


def _harness(tmp_path: Path, repo_root: Path, body: str = GOOD, status: int = 200) -> BotHarness:
    def feed(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body)

    return BotHarness(tmp_path, repo_root, transport=make_transport({"feeds.example.com": feed}))


async def test_valid_feed_saved_only_after_confirmation(tmp_path: Path, repo_root: Path) -> None:
    h = _harness(tmp_path, repo_root)
    out = await h.say(f"/feed_add {URL} Jobs")
    assert "Python contractor" in out[0]
    assert "No feeds" in (await h.say("/feeds"))[0]  # nothing saved yet
    await h.say("yes")
    assert URL in (await h.say("/feeds"))[0]
    from jobharness.bot.user_settings import load_settings

    s = load_settings(h.services.config_path, h.data_dir)
    assert s.ingest is not None and s.ingest.rss_feeds == [URL]


async def test_declined_feed_is_not_saved(tmp_path: Path, repo_root: Path) -> None:
    h = _harness(tmp_path, repo_root)
    await h.script(f"/feed_add {URL}", "no")
    assert "No feeds" in (await h.say("/feeds"))[0]


async def test_invalid_and_empty_feeds_refused(tmp_path: Path, repo_root: Path) -> None:
    bad = _harness(tmp_path / "a", repo_root, body="<html>not rss")
    assert "not valid RSS" in (await bad.say(f"/feed_add {URL}"))[0]
    empty = _harness(tmp_path / "b", repo_root, body=rss_xml([]))
    assert "no items" in (await empty.say(f"/feed_add {URL}"))[0]
    err = _harness(tmp_path / "c", repo_root, status=500)
    assert "HTTP 500" in (await err.say(f"/feed_add {URL}"))[0]
    assert "http" in (await err.say("/feed_add ftp://x"))[0]


async def test_duplicate_refused_and_remove(tmp_path: Path, repo_root: Path) -> None:
    h = _harness(tmp_path, repo_root)
    await h.script(f"/feed_add {URL} Jobs", "yes")
    assert "already added" in (await h.say(f"/feed_add {URL}"))[0]
    assert "removed" in (await h.say("/feed_remove Jobs"))[0]
    assert "No feeds" in (await h.say("/feeds"))[0]
    assert "No such feed" in (await h.say("/feed_remove Jobs"))[0]
