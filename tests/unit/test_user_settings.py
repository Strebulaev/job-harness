"""Step 4.4: preferences wizard and settings overlay."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobharness.bot.testing import BotHarness
from jobharness.bot.user_settings import (
    MissingProfileError,
    deep_merge,
    load_runtime,
    load_settings,
    save_user_settings,
)

PREFS = [
    "/preferences", "2500", "5000", "15", "30", "Europe/Berlin", "10:00-18:00",
    "us, de", "ru", "contractor, b2b", "anonymized", "handson_descriptor", "30",
]


def test_deep_merge_replaces_lists_and_merges_dicts() -> None:
    base = {"a": {"b": 1, "c": [1, 2]}, "d": 1}
    assert deep_merge(base, {"a": {"c": [9]}}) == {"a": {"b": 1, "c": [9]}, "d": 1}


async def test_preferences_override_base_values(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    out = await h.script(*PREFS)
    assert "Preferences saved" in out[-1]
    s = load_settings(h.services.config_path, h.data_dir)
    assert s.router.rate_floor_usd_month == 2500 and s.router.rate_ceiling_usd_month == 5000
    assert s.router.countries_allow == ["US", "DE"] and s.router.countries_deny == ["RU"]
    assert s.principal.timezone == "Europe/Berlin" and s.bot.search_interval_minutes == 30
    pos = yaml.safe_load((h.data_dir / "positioning.yaml").read_text())
    assert pos["employer_display"] == "anonymized" and pos["hours_week"] == {"min": 15.0, "max": 30.0}
    assert s.ingest is not None and s.ingest.rss_feeds == []  # bot mode starts without feeds


async def test_invalid_values_are_rejected_and_not_saved(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    bad = [*PREFS]
    bad[1], bad[2] = "5000", "2500"  # floor above ceiling
    out = await h.script(*bad)
    assert "Not saved" in out[-1]
    assert not (h.data_dir / "user_settings.yaml").exists()


def test_unknown_key_is_rejected(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    with pytest.raises(ValueError):
        save_user_settings(h.services.config_path, h.data_dir, {"router": {"nonsense": 1}})
    assert not (h.data_dir / "user_settings.yaml").exists()


def test_load_runtime_needs_profile_then_builds(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    with pytest.raises(MissingProfileError):
        load_runtime(h.services.config_path, h.data_dir)
    (h.data_dir / "profile.yaml").write_text(
        (repo_root / "config" / "profile.example.yaml").read_text(), encoding="utf-8"
    )
    rt = load_runtime(h.services.config_path, h.data_dir)
    assert rt.profile.identity.full_name and rt.archetypes and rt.positioning.hours_week.max > 0
