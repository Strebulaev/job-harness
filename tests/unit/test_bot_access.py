"""Step 4.1: owner-only access and basic commands."""

from __future__ import annotations

from pathlib import Path

from jobharness.bot.app import WELCOME
from jobharness.bot.testing import BotHarness


async def test_owner_gets_start_and_help(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    assert await h.say("/start") == [WELCOME]
    help_text = (await h.say("/help"))[0]
    assert "/profile_start" in help_text and "/run" in help_text


async def test_non_owner_gets_nothing(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    assert await h.say("/start", user_id=999) == []
    assert await h.say("hello", user_id=999) == []
    assert h.messenger.sent == []


async def test_non_owner_callback_ignored(tmp_path: Path, repo_root: Path) -> None:
    from jobharness.bot.core import Incoming

    h = BotHarness(tmp_path, repo_root)
    await h.core.handle(Incoming(999, 999, 1, callback_data="dlv:applied:1"))
    assert h.messenger.sent == []


async def test_unknown_command_and_plain_text(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    assert "Unknown command" in (await h.say("/nope"))[0]
    assert "did not understand" in (await h.say("hello there"))[0]


async def test_handler_errors_are_reported_generically(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)

    @h.core.command("boom")
    async def boom(ctx, args):  # type: ignore[no-untyped-def]
        raise RuntimeError("secret-token-123")

    out = await h.say("/boom")
    assert out and "secret-token-123" not in out[0]
