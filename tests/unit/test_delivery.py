"""Step 5.2: delivery to chat."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from jobharness.bot.delivery import deliver_ready
from jobharness.bot.testing import cycle_harness
from jobharness.bot.user_settings import load_runtime
from jobharness.db.models import Delivery, Job
from jobharness.pipeline.cycle import CycleDeps, run_cycle


async def _ready(tmp_path: Path, repo_root: Path, **kw):  # type: ignore[no-untyped-def]
    h = cycle_harness(tmp_path, repo_root, **kw)
    rt = load_runtime(h.services.config_path, h.data_dir)
    prov = h.services.provider_factory(rt, h.services)
    await run_cycle(CycleDeps(rt, prov, lambda: None, h.fixed_now, h.services.transport))
    return h, rt


def _status(h, title_part: str) -> str:  # type: ignore[no-untyped-def]
    with h.session_factory() as s:
        return next(j.status for j in s.execute(select(Job)).scalars() if title_part in (j.title or ""))


async def test_one_job_is_delivered_as_message_resume_and_cover(tmp_path: Path, repo_root: Path) -> None:
    h, rt = await _ready(tmp_path, repo_root)
    n = await deliver_ready(rt, h.messenger, h.chat_id, h.fixed_now)
    assert n == 1
    msg = h.messenger.sent[0]
    assert "RAG/LLM Engineer" in msg.text and "https://remoteok.com/1234567" in msg.text
    assert msg.buttons is not None and [b.data for b in msg.buttons[0]] == [
        f"dlv:applied:{_job_id(h)}", f"dlv:skip:{_job_id(h)}"
    ]
    assert len(h.messenger.documents()) == 1
    assert any("Dear Hiring Team" in t and "independent contractor" in t for t in h.messenger.texts())
    assert _status(h, "RAG") == "delivered"


def _job_id(h) -> int:  # type: ignore[no-untyped-def]
    with h.session_factory() as s:
        return next(j.id for j in s.execute(select(Job)).scalars() if "RAG" in (j.title or ""))


async def test_nothing_is_redelivered_and_cap_holds(tmp_path: Path, repo_root: Path) -> None:
    h, rt = await _ready(tmp_path, repo_root)
    assert await deliver_ready(rt, h.messenger, h.chat_id, h.fixed_now) == 1
    assert await deliver_ready(rt, h.messenger, h.chat_id, h.fixed_now) == 0
    capped = rt.settings.model_copy(deep=True)
    capped.bot.max_deliveries_per_day = 1
    rt.settings = capped
    assert await deliver_ready(rt, h.messenger, h.chat_id, h.fixed_now) == 0


async def test_send_failure_leaves_job_queued(tmp_path: Path, repo_root: Path) -> None:
    h, rt = await _ready(tmp_path, repo_root)
    h.messenger.fail_send = True
    assert await deliver_ready(rt, h.messenger, h.chat_id, h.fixed_now) == 0
    assert _status(h, "RAG") == "queued"
    h.messenger.fail_send = False
    assert await deliver_ready(rt, h.messenger, h.chat_id, h.fixed_now) == 1


async def test_applied_and_skip_buttons(tmp_path: Path, repo_root: Path) -> None:
    h, rt = await _ready(tmp_path, repo_root)
    await deliver_ready(rt, h.messenger, h.chat_id, h.fixed_now)
    jid = _job_id(h)
    await h.press(f"dlv:applied:{jid}")
    assert _status(h, "RAG") == "applied"
    assert h.messenger.edits and "applied" in h.messenger.edits[-1][2]
    with h.session_factory() as s:
        assert s.execute(select(Delivery)).scalars().one().outcome == "applied"
    await h.press(f"dlv:skip:{jid}")  # second press is harmless
    assert "already handled" in h.messenger.last_text()
