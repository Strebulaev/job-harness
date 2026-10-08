"""Step 6.2: documented commands exist (decision 0006: docs are done when accurate)."""

from __future__ import annotations

import re
from pathlib import Path

from typer.main import get_command

from jobharness.bot.testing import BotHarness
from jobharness.cli import app

DOCS = ("README.md", "docs/RUNBOOK.md")


def _text(repo_root: Path) -> str:
    return "\n".join((repo_root / d).read_text(encoding="utf-8") for d in DOCS)


async def test_documented_chat_commands_exist(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    known = set(h.core.commands)
    documented = set(re.findall(r"`/([a-z_]+)", _text(repo_root)))
    assert documented, "docs should mention chat commands"
    assert documented <= known, f"documented but missing: {sorted(documented - known)}"


def test_documented_jh_commands_exist(repo_root: Path) -> None:
    root = get_command(app)
    groups = set(root.commands)  # type: ignore[attr-defined]
    documented = set(re.findall(r"`(?:uv run )?jh ([a-z-]+)", _text(repo_root)))
    assert documented
    assert documented <= groups, f"documented but missing: {sorted(documented - groups)}"
