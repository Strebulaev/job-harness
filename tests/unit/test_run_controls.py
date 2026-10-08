"""Step 5.3: /run, /pause, /search_now, /status and scheduler restore."""

from __future__ import annotations

from pathlib import Path

from jobharness.bot.app import build_core
from jobharness.bot.run_controls import JOB_ID, restore
from jobharness.bot.testing import FEED_URL, cycle_harness


async def test_run_lists_missing_prerequisites_then_starts(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root)
    (h.data_dir / "profile.yaml").unlink()
    h.set_overlay({"ingest": {"rss_feeds": []}})
    out = (await h.say("/run"))[0]
    assert "Not ready" in out and "profile" in out and "source" in out
    assert JOB_ID not in h.scheduler.jobs

    h.install_example_profile(repo_root)
    out = (await h.say("/run"))[0]
    assert "source" in out and "profile" not in out

    h.set_overlay({"ingest": {"rss_feeds": [FEED_URL]}})
    texts = await h.say("/run")
    assert "Search started" in texts[0] and "Cycle done" in " ".join(texts)
    assert h.scheduler.jobs[JOB_ID][0] == 60  # default interval minutes
    assert len(h.messenger.documents()) == 1  # first delivery happened


async def test_pause_stops_scheduler_and_status_reports(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root)
    await h.say("/run")
    assert "Search: active" in (await h.say("/status"))[0]
    assert "paused" in (await h.say("/pause"))[0]
    assert JOB_ID not in h.scheduler.jobs
    status = (await h.say("/status"))[0]
    assert "Search: paused" in status and "Delivered today: 1/10" in status


async def test_scheduler_tick_runs_a_cycle(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root)
    await h.say("/run")
    before = len(h.messenger.sent)
    await h.scheduler.fire()
    assert len(h.messenger.sent) == before  # nothing new: no duplicates


async def test_active_state_is_restored_after_restart(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root)
    await h.say("/run")
    h.scheduler.jobs.clear()  # process restarted: scheduler is empty
    h.core = build_core(h.services, h.messenger)
    assert restore(h.services, h.messenger) is True
    assert JOB_ID in h.scheduler.jobs


async def test_search_now_runs_once(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root)
    out = await h.say("/search_now")
    assert any("Cycle done" in t for t in out)


async def test_total_failure_notifies_owner_once(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root)

    def broken(_rt, _svc):  # type: ignore[no-untyped-def]
        raise RuntimeError("provider unavailable")

    h.services.provider_factory = broken
    await h.say("/run")
    await h.scheduler.fire()
    await h.scheduler.fire()
    failures = [t for t in h.messenger.texts() if t.startswith("Search cycle failed")]
    assert len(failures) == 1
