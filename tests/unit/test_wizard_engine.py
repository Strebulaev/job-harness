"""Step 4.2: resumable conversation engine."""

from __future__ import annotations

from pathlib import Path

from jobharness.bot.app import build_core
from jobharness.bot.testing import BotHarness
from jobharness.bot.wizard import Step, Wizard


def _number(text: str, _a: dict) -> int:  # type: ignore[type-arg]
    if not text.strip().isdigit():
        raise ValueError("Send a whole number.")
    return int(text)


def _register(h: BotHarness, done: list[dict]) -> None:  # type: ignore[type-arg]
    async def on_complete(ctx, answers):  # type: ignore[no-untyped-def]
        done.append(dict(answers))
        await ctx.reply("done")

    h.core.wizard_runner.register(Wizard("demo", [
        Step("age", "Your age?", _number),
        Step("nick", "Nickname?", optional=True, default="anon"),
        Step("city", "City?"),
    ], on_complete))

    @h.core.command("demo")
    async def demo(ctx, args):  # type: ignore[no-untyped-def]
        await h.core.wizard_runner.start(ctx, "demo")


async def test_completes_step_by_step(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    done: list[dict] = []  # type: ignore[type-arg]
    _register(h, done)
    out = await h.script("/demo", "30", "bob", "Berlin")
    assert out[-1] == "done" and done == [{"age": 30, "nick": "bob", "city": "Berlin"}]


async def test_invalid_input_reprompts(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    _register(h, [])
    await h.say("/demo")
    out = await h.say("abc")
    assert "whole number" in out[0]
    assert "Nickname" in (await h.say("30"))[0]


async def test_back_skip_cancel(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    done: list[dict] = []  # type: ignore[type-arg]
    _register(h, done)
    await h.say("/demo")
    assert "required" in (await h.say("/skip"))[0]
    await h.say("30")
    assert "Your age?" in (await h.say("/back"))[0]
    await h.script("30", "/skip", "Rome")
    assert done[-1]["nick"] == "anon"
    await h.say("/demo")
    assert "Cancelled" in (await h.say("/cancel"))[0]
    assert await h.say("/skip") == ["Nothing to do right now. Send /help."]


async def test_state_survives_restart(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    done: list[dict] = []  # type: ignore[type-arg]
    _register(h, done)
    await h.script("/demo", "41")
    # simulate a restart: a brand-new core over the same database
    h.core = build_core(h.services, h.messenger)
    _register(h, done)
    out = await h.script("Ann", "Oslo")  # nickname, city
    assert done == [{"age": 41, "nick": "Ann", "city": "Oslo"}] and out[-1] == "done"
