"""Step 5.1: one search cycle over mocked sources with an offline LLM."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select

from jobharness.bot.testing import cycle_harness
from jobharness.bot.user_settings import load_runtime
from jobharness.db.models import Document, EvalRun, Job, LLMCall
from jobharness.pipeline.cycle import CycleDeps, run_cycle


def _deps(h, provider=None):  # type: ignore[no-untyped-def]
    rt = load_runtime(h.services.config_path, h.data_dir)
    prov = provider or h.services.provider_factory(rt, h.services)
    return CycleDeps(rt, prov, lambda: None, h.fixed_now, h.services.transport)


def _statuses(h) -> dict[str, str]:  # type: ignore[no-untyped-def]
    with h.session_factory() as s:
        return {j.title: j.status for j in s.execute(select(Job)).scalars()}


async def test_cycle_produces_documents_for_shortlisted_only(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root)
    report = await run_cycle(_deps(h))
    assert report.refused is None and report.fetched == 2 and report.inserted == 2, report
    assert report.parsed == 2 and report.rejected == 1 and report.shortlisted == 1
    assert report.composed_ok == 1 and report.gated_fail == 0, report.errors
    assert sorted(_statuses(h).values()) == ["queued", "rejected"]
    with h.session_factory() as s:
        docs = s.execute(select(Document)).scalars().all()
        assert sorted(d.kind for d in docs) == ["cover", "resume"]
        assert all(d.eval_pass for d in docs)
        assert s.execute(select(func.count()).select_from(EvalRun)).scalar_one() == 1


async def test_second_cycle_creates_no_duplicates(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root)
    await run_cycle(_deps(h))
    again = await run_cycle(_deps(h))
    assert again.inserted == 0 and again.composed_ok == 0 and again.parsed == 0
    with h.session_factory() as s:
        assert s.execute(select(func.count()).select_from(Job)).scalar_one() == 2
        assert s.execute(select(func.count()).select_from(Document)).scalar_one() == 2


async def test_max_jobs_per_cycle_caps_work(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root, overlay={"bot": {"max_jobs_per_cycle": 1}})
    first = await run_cycle(_deps(h))
    assert first.parsed == 1
    second = await run_cycle(_deps(h))
    assert second.parsed == 1
    assert "new" not in _statuses(h).values()


async def test_token_budget_stops_llm_stages(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root, overlay={"llm": {"daily_token_budget": 1000}})
    with h.session_factory() as s:
        s.add(LLMCall(purpose="x", input_tokens=900, output_tokens=900, ok=True,
                      created_at=h.fixed_now.isoformat()))
        s.commit()
    report = await run_cycle(_deps(h))
    assert report.parsed == 0 and report.skipped_budget == 2
    # next day the budget is available again
    h.fixed_now = h.fixed_now + timedelta(days=1)
    assert (await run_cycle(_deps(h))).parsed == 2


async def test_one_failing_job_does_not_abort_the_cycle(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root, fail_on="g03")
    report = await run_cycle(_deps(h))
    assert report.parse_failed == 1 and report.composed_ok == 1
    assert any("scripted parse failure" in e for e in report.errors)


async def test_refuses_without_sources_or_profile_content(tmp_path: Path, repo_root: Path) -> None:
    h = cycle_harness(tmp_path, repo_root)
    h.set_overlay({"ingest": {"rss_feeds": []}})
    assert "no sources" in (await run_cycle(_deps(h))).refused  # type: ignore[operator]
