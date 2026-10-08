"""Test harness: a scripted chat with the bot core, entirely offline."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import httpx

from jobharness.bot.app import build_core
from jobharness.bot.core import Incoming, Services
from jobharness.bot.messenger import FakeMessenger
from jobharness.bot.run_controls import FakeScheduler
from jobharness.db.session import create_schema, init_session_factory, make_engine
from jobharness.llm.provider import LLMProvider
from jobharness.llm.scripted_provider import ScriptedProvider
from jobharness.secrets.store import SecretStore, generate_master_key

OWNER = 4242


class BotHarness:
    def __init__(
        self,
        tmp_path: Path,
        repo_root: Path,
        *,
        provider: LLMProvider | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        owner_id: int = OWNER,
        clock: datetime | None = None,
    ) -> None:
        self.data_dir = tmp_path / "data"
        config_dir = tmp_path / "config"
        shutil.copytree(repo_root / "config" / "archetypes", config_dir / "archetypes")
        shutil.copy(repo_root / "config" / "config.example.yaml", config_dir / "config.yaml")
        shutil.copy(repo_root / "config" / "positioning.example.yaml", config_dir / "positioning.yaml")
        engine = make_engine(self.data_dir / "jobharness.db")
        create_schema(engine)
        self.session_factory = init_session_factory(engine)
        self.fixed_now = clock or datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
        self.services = Services(
            session_factory=self.session_factory,
            secrets=SecretStore(self.session_factory, generate_master_key()),
            config_path=config_dir / "config.yaml",
            data_dir=self.data_dir,
            owner_id=owner_id,
            transport=transport,
            provider_factory=(lambda _rt, _svc: provider) if provider is not None else None,
            clock=lambda: self.fixed_now,
        )
        self.scheduler = FakeScheduler()
        self.services.extras["scheduler"] = self.scheduler
        self.messenger = FakeMessenger()
        self.core = build_core(self.services, self.messenger)
        self.owner_id = owner_id
        self.chat_id = owner_id
        self._msg = 0

    async def say(self, text: str, *, user_id: int | None = None) -> list[str]:
        """Send a message; return the texts the bot sent in response."""
        before = len(self.messenger.sent)
        self._msg += 1
        await self.core.handle(
            Incoming(user_id or self.owner_id, self.chat_id, self._msg, text=text)
        )
        return [s.text for s in self.messenger.sent[before:] if s.kind == "text"]

    async def press(self, data: str) -> None:
        self._msg += 1
        await self.core.handle(
            Incoming(self.owner_id, self.chat_id, self._msg, callback_data=data)
        )

    def install_example_profile(self, repo_root: Path) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(repo_root / "config" / "profile.example.yaml", self.data_dir / "profile.yaml")

    def set_overlay(self, patch: dict[str, Any]) -> None:
        from jobharness.bot.user_settings import save_user_settings

        save_user_settings(self.services.config_path, self.data_dir, patch)

    async def script(self, *lines: str) -> list[str]:
        out: list[str] = []
        for line in lines:
            out += await self.say(line)
        return out




# --------------------------------------------------------------- fake world
Handler = Callable[[httpx.Request], httpx.Response]


def make_transport(routes: dict[str, Handler]) -> httpx.MockTransport:
    """Route mocked HTTP by host name; unknown hosts get 404."""

    def handler(req: httpx.Request) -> httpx.Response:
        fn = routes.get(req.url.host)
        return fn(req) if fn else httpx.Response(404, text="unknown host in test")

    return httpx.MockTransport(handler)


def rss_xml(items: list[tuple[str, str, str]]) -> str:
    body = "".join(
        f"<item><title>{escape(t)}</title><link>{escape(link)}</link>"
        f"<description>{escape(d)}</description></item>"
        for t, link, d in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{body}</channel></rss>'


def golden_job(repo_root: Path, name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (repo_root / "eval_data" / "golden_jobs" / f"{name}.json").read_text(encoding="utf-8")
    )
    return data


def golden_provider(repo_root: Path, names: list[str], fail_on: str | None = None) -> ScriptedProvider:
    """Offline LLM: jd_parse returns each golden job's labelled parse; composers
    fall back to verbatim facts; judges are happy. ``fail_on`` makes jd_parse
    raise for the golden job whose id contains that string."""
    jobs = [golden_job(repo_root, n) for n in names]

    def jd_parse(*, user: str, **_: object) -> dict[str, Any]:
        for g in jobs:
            if g["jd_raw"].strip() in user:
                if fail_on and fail_on in g["id"]:
                    raise RuntimeError("scripted parse failure")
                parsed: dict[str, Any] = g["expected_jd_parsed"]
                return parsed
        return {"title": "Unknown role"}

    def offline(**_: object) -> dict[str, Any]:
        raise RuntimeError("offline")

    return ScriptedProvider({
        "jd_parse": jd_parse,
        "resume_compose": offline,
        "cover_compose": offline,
        "judge_resume": lambda **_: {"scores": {"relevance": 4, "specificity": 4}, "rationale": "ok"},
        "judge_cover": lambda **_: {"scores": {"personalization": 4}, "rationale": "ok"},
        "fit_sound_judge": lambda **_: {"verdict": "on_target", "rationale": "ok"},
    })


FEED_URL = "https://feeds.example.com/jobs.xml"


def golden_feed(repo_root: Path, names: list[str]) -> str:
    """RSS feed whose items are the golden jobs' descriptions."""
    items = []
    for n in names:
        g = golden_job(repo_root, n)
        items.append((g["expected_jd_parsed"]["title"], g["url"], g["jd_raw"].strip()))
    return rss_xml(items)


def cycle_harness(
    tmp_path: Path,
    repo_root: Path,
    names: list[str] | None = None,
    *,
    fail_on: str | None = None,
    overlay: dict[str, Any] | None = None,
) -> BotHarness:
    """A harness with an example profile, one RSS feed of golden jobs and an offline LLM."""
    names = names or ["g01_rag_remote_ok", "g03_employee_rejected"]
    body = golden_feed(repo_root, names)
    h = BotHarness(
        tmp_path, repo_root,
        provider=golden_provider(repo_root, names, fail_on=fail_on),
        transport=make_transport({"feeds.example.com": lambda r: httpx.Response(200, text=body)}),
    )
    h.install_example_profile(repo_root)
    h.set_overlay({"ingest": {"rss_feeds": [FEED_URL]}, **(overlay or {})})
    return h


__all__ = [
    "FEED_URL",
    "OWNER",
    "BotHarness",
    "cycle_harness",
    "golden_feed",
    "golden_job",
    "golden_provider",
    "make_transport",
    "rss_xml",
]
