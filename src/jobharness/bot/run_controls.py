"""Run controls and scheduler (plan step 5.3): /run /pause /search_now /status."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import yaml

from jobharness.bot.core import BotCore, Ctx, Services
from jobharness.bot.delivery import deliver_ready, delivered_today
from jobharness.bot.messenger import Messenger
from jobharness.bot.profile_wizard import missing_for_run
from jobharness.bot.provider_commands import OPENROUTER_SECRET, SUPERJOB_SECRET, models_configured
from jobharness.bot.user_settings import load_runtime, load_settings, profile_path
from jobharness.pipeline.cycle import CycleDeps, CycleReport, run_cycle, tokens_used_today
from jobharness.schemas.profile import Profile

_log = logging.getLogger(__name__)
STATE_KEY = "search:state"
JOB_ID = "search-cycle"


class Scheduler(Protocol):
    def add_interval(self, job_id: str, minutes: int, fn: Callable[[], Awaitable[None]]) -> None: ...

    def remove(self, job_id: str) -> None: ...


@dataclass
class FakeScheduler:
    jobs: dict[str, tuple[int, Callable[[], Awaitable[None]]]] = field(default_factory=dict)

    def add_interval(self, job_id: str, minutes: int, fn: Callable[[], Awaitable[None]]) -> None:
        self.jobs[job_id] = (minutes, fn)

    def remove(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)

    async def fire(self, job_id: str = JOB_ID) -> None:
        await self.jobs[job_id][1]()


class ApScheduler:
    """APScheduler-backed scheduler (not unit-tested; thin wrapper)."""

    def __init__(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        self._s = AsyncIOScheduler()

    def start(self) -> None:
        self._s.start()

    def add_interval(self, job_id: str, minutes: int, fn: Callable[[], Awaitable[None]]) -> None:
        self._s.add_job(fn, "interval", minutes=minutes, id=job_id, replace_existing=True,
                        max_instances=1, coalesce=True)

    def remove(self, job_id: str) -> None:
        if self._s.get_job(job_id) is not None:
            self._s.remove_job(job_id)


def _state(services: Services) -> dict[str, Any]:
    st = services.state.get(STATE_KEY)
    return st if isinstance(st, dict) else {"active": False}


def check_ready(services: Services) -> list[str]:
    """Human-readable list of what is still missing before a search can run."""
    problems: list[str] = []
    pp = profile_path(services.data_dir)
    profile: Profile | None = None
    if not pp.exists():
        problems.append("a profile (/profile_start)")
    else:
        profile = Profile.model_validate(yaml.safe_load(pp.read_text(encoding="utf-8")))
        problems += missing_for_run(profile)
    settings = load_settings(services.config_path, services.data_dir)
    if services.provider_factory is None:
        if settings.llm.provider == "openrouter" and not services.secrets.get(OPENROUTER_SECRET):
            problems.append("a connected OpenRouter key (/connect openrouter)")
        unset = models_configured(settings.llm.models.model_dump())
        if unset:
            problems.append("models for: " + ", ".join(unset) + " (/models set <role> <model-id>)")
    have_key = bool(services.secrets.get(SUPERJOB_SECRET))
    has_feeds = bool(settings.ingest and settings.ingest.rss_feeds)
    if not have_key and not has_feeds:
        problems.append("a source: /connect superjob or /feed_add <url>")
    return problems


def _summary(report: CycleReport, delivered: int) -> str:
    if report.refused:
        return f"Cycle skipped: {report.refused}."
    parts = [
        f"fetched {report.fetched}", f"new {report.inserted}", f"parsed {report.parsed}",
        f"shortlisted {report.shortlisted}", f"documents ready {report.composed_ok}",
        f"failed gates {report.gated_fail}", f"delivered {delivered}",
    ]
    text = "Cycle done: " + ", ".join(parts) + "."
    if report.errors:
        text += f" {len(report.errors)} problem(s); last: {report.errors[-1]}"
    return text


async def run_search_cycle(services: Services, messenger: Messenger, chat_id: int) -> str:
    """Run one cycle + delivery; returns a short summary. Never raises."""
    state = _state(services)
    try:
        rt = load_runtime(services.config_path, services.data_dir)
        factory = services.provider_factory
        if factory is None:
            from jobharness.bot.app import default_provider_factory

            factory = default_provider_factory
        provider = factory(rt, services)
        now = services.clock()
        deps = CycleDeps(
            rt, provider, lambda: services.secrets.get(SUPERJOB_SECRET), now, services.transport
        )
        report = await run_cycle(deps)
        delivered = await deliver_ready(rt, messenger, chat_id, now)
        summary = _summary(report, delivered)
        state.update(last_run_at=now.isoformat(), last_report=report.as_dict(),
                     last_summary=summary, last_error=None)
        if report.skipped_budget and state.get("budget_notified_on") != now.date().isoformat():
            state["budget_notified_on"] = now.date().isoformat()
            services.state.set(STATE_KEY, state)
            await messenger.send_text(chat_id, "Daily token budget reached; paused LLM work until tomorrow.")
        services.state.set(STATE_KEY, state)
        return summary
    except Exception as e:
        msg = f"{type(e).__name__}: {str(e)[:160]}"
        _log.warning("search cycle failed: %s", msg)
        previous = state.get("last_error")
        state["last_error"] = msg
        services.state.set(STATE_KEY, state)
        if previous != msg:  # notify once per distinct failure
            await messenger.send_text(chat_id, f"Search cycle failed: {msg}")
        return f"Cycle failed: {msg}"


def schedule(services: Services, messenger: Messenger, chat_id: int) -> None:
    scheduler: Scheduler | None = services.extras.get("scheduler")
    if scheduler is None:
        return
    minutes = load_settings(services.config_path, services.data_dir).bot.search_interval_minutes

    async def tick() -> None:
        await run_search_cycle(services, messenger, chat_id)

    scheduler.add_interval(JOB_ID, minutes, tick)


def restore(services: Services, messenger: Messenger) -> bool:
    """Resume the scheduler after a restart if the search was active."""
    st = _state(services)
    if st.get("active") and st.get("chat_id"):
        schedule(services, messenger, int(st["chat_id"]))
        return True
    return False


def register_run_controls(core: BotCore) -> None:
    @core.command("run", "start the periodic job search")
    async def run(ctx: Ctx, _args: str) -> None:
        problems = check_ready(ctx.services)
        if problems:
            await ctx.reply("Not ready yet. Still needed:\n- " + "\n- ".join(problems))
            return
        st = _state(ctx.services)
        st.update(active=True, chat_id=ctx.chat_id)
        ctx.services.state.set(STATE_KEY, st)
        schedule(ctx.services, ctx.messenger, ctx.chat_id)
        minutes = load_settings(ctx.services.config_path, ctx.services.data_dir).bot.search_interval_minutes
        await ctx.reply(f"Search started; I will look every {minutes} minutes. Running the first cycle now.")
        await ctx.reply(await run_search_cycle(ctx.services, ctx.messenger, ctx.chat_id))

    @core.command("pause", "stop the periodic search")
    async def pause(ctx: Ctx, _args: str) -> None:
        st = _state(ctx.services)
        st["active"] = False
        ctx.services.state.set(STATE_KEY, st)
        scheduler: Scheduler | None = ctx.services.extras.get("scheduler")
        if scheduler is not None:
            scheduler.remove(JOB_ID)
        await ctx.reply("Search paused. /run resumes it.")

    @core.command("search_now", "run one search cycle immediately")
    async def search_now(ctx: Ctx, _args: str) -> None:
        problems = check_ready(ctx.services)
        if problems:
            await ctx.reply("Not ready yet. Still needed:\n- " + "\n- ".join(problems))
            return
        await ctx.reply(await run_search_cycle(ctx.services, ctx.messenger, ctx.chat_id))

    @core.command("status", "show search status")
    async def status(ctx: Ctx, _args: str) -> None:
        st = _state(ctx.services)
        settings = load_settings(ctx.services.config_path, ctx.services.data_dir)
        now = ctx.services.clock()
        lines = [f"Search: {'active' if st.get('active') else 'paused'}"]
        lines.append(f"Last cycle: {st.get('last_run_at') or 'never'}")
        if st.get("last_summary"):
            lines.append(str(st["last_summary"]))
        lines.append(
            f"Delivered today: {delivered_today(now)}/{settings.bot.max_deliveries_per_day}; "
            f"tokens today: {tokens_used_today(now)}/{settings.llm.daily_token_budget}"
        )
        rep = st.get("last_report") or {}
        if rep.get("gated_fail"):
            lines.append(f"Jobs that failed quality checks (not delivered): {rep['gated_fail']}")
        if st.get("last_error"):
            lines.append(f"Last error: {st['last_error']}")
        await ctx.reply("\n".join(lines))


__all__ = [
    "ApScheduler",
    "FakeScheduler",
    "check_ready",
    "register_run_controls",
    "restore",
    "run_search_cycle",
    "schedule",
]
