"""Step 4.3: profile wizard builds a valid profile from chat answers."""

from __future__ import annotations

from pathlib import Path

import yaml

from jobharness.bot.profile_wizard import slug
from jobharness.bot.testing import BotHarness
from jobharness.schemas.profile import load_profile, validate_profile

START = [
    "/profile_start",
    # identity
    "Jane A. Doe", "jane@example.com", "/skip", "Kyiv", "UA", "Europe/Kiev",
    "English C1, Russian native", "/skip", "/skip",
    # summary
    "Backend engineer with 12 years of experience.", "backend, python",
    # role
    "Acme Corp", "CTO", "2019-03", "2024-08", "full_time", "/skip", "/skip",
    "Designed an ingestion pipeline handling 2M req/day.", "backend, python", "/skip",
    "req/day=2000000", "internal dashboard", "no",
    # skills
    "Python:expert:12, SQL:proficient:8",
    # disclosure
    "no", "/skip",
]


async def test_full_guided_setup_writes_valid_profile(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    out = await h.script(*START)
    path = h.data_dir / "profile.yaml"
    assert path.exists(), out
    profile = load_profile(str(path))
    assert validate_profile(profile) == []
    assert profile.identity.full_name == "Jane A. Doe"
    assert profile.experience[0].id == "exp.acme-corp"
    bullet = profile.experience[0].bullets[0]
    assert bullet.id == "exp.acme-corp.b1" and bullet.evidence == "internal dashboard"
    assert bullet.metrics[0].value == 2000000
    assert [s.id for s in profile.skills] == ["skill.python", "skill.sql"]
    assert any("/preferences" in t for t in out)


async def test_metric_requires_evidence_and_bad_dates_reprompt(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    await h.script("/profile_role", "Acme", "CTO")
    assert "YYYY-MM" in (await h.say("March 2019"))[0]
    await h.script("2019-03", "present", "b2b", "/skip", "/skip", "Did a thing", "/skip", "/skip")
    assert "verified" in (await h.say("x=1"))[0]


async def test_ids_unique_on_repeat_and_profile_status(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    await h.script(*START)
    role = ["/profile_role", "Acme Corp", "Engineer", "2015-01", "2018-12", "full_time", "/skip",
            "/skip", "Built things.", "/skip", "/skip", "/skip", "no"]
    await h.script(*role)
    ids = [e["id"] for e in yaml.safe_load((h.data_dir / "profile.yaml").read_text())["experience"]]
    assert len(ids) == len(set(ids)) == 2
    status = (await h.say("/profile"))[0]
    assert "Roles: 2" in status
    await h.say("/profile_export")
    assert h.messenger.documents()[-1].path == h.data_dir / "profile.yaml"


async def test_invalid_input_is_rejected_with_reason(tmp_path: Path, repo_root: Path) -> None:
    h = BotHarness(tmp_path, repo_root)
    await h.script("/profile_identity", "Jane", "not-an-email")
    assert "email" in h.messenger.last_text()
    await h.script("jane@example.com", "/skip", "Kyiv", "UA")
    assert "timezone" in (await h.say("Mars/Base"))[0].lower()


def test_slug() -> None:
    assert slug("Acme Corp, Inc.") == "acme-corp-inc"
