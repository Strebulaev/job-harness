"""Step 2.4: mutation-style corruptions must be blocked by the gates (spec §18)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from jobharness.compose.cover import compose_cover
from jobharness.compose.resume import compose_resume
from jobharness.eval.gates import run_gates
from jobharness.llm.scripted_provider import ScriptedProvider
from jobharness.schemas.archetype import load_archetypes
from jobharness.schemas.documents import ResumeContent
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import load_positioning
from jobharness.schemas.profile import load_profile

ROOT = Path(__file__).resolve().parents[2]
PROFILE = load_profile(str(ROOT / "config" / "profile.example.yaml"))
POSITIONING = load_positioning(ROOT / "config" / "positioning.example.yaml")
ARCH = load_archetypes(ROOT / "config" / "archetypes")["a_ai_llm_engineer"]
JD = JDParsed(title="LLM Engineer", must_have=["Python"])


def _change_number(c: ResumeContent) -> None:
    b = c.experience[0].bullets[0]
    b.text = b.text.replace("2M", "7M").replace("25%", "55%").replace("40%", "80%")
    if "7M" not in b.text and "55%" not in b.text and "80%" not in b.text:
        b.text += " Handled 7M items."


def _add_tech(c: ResumeContent) -> None:
    c.experience[0].bullets[0].text += " Implemented with Kafka and Terraform."


def _shift_date(c: ResumeContent) -> None:
    c.experience[0].start = "2016-03"


def _change_title(c: ResumeContent) -> None:
    c.experience[0].title_display = "VP of Engineering"


CORRUPTIONS: list[tuple[str, Callable[[ResumeContent], None], str]] = [
    ("number", _change_number, "G1"),
    ("tech", _add_tech, "G1"),
    ("date", _shift_date, "G2"),
    ("title", _change_title, "G3"),
]


@pytest.mark.parametrize(("name", "corrupt", "gate"), CORRUPTIONS, ids=[c[0] for c in CORRUPTIONS])
async def test_corruption_is_blocked(
    name: str, corrupt: Callable[[ResumeContent], None], gate: str
) -> None:
    def boom(**_: object) -> dict[str, object]:
        raise RuntimeError("offline")

    provider = ScriptedProvider({"resume_compose": boom, "cover_compose": boom})
    resume = await compose_resume(
        PROFILE, ARCH, POSITIONING, JD, provider, model="m", today=date(2026, 10, 8)
    )
    cover = await compose_cover(
        PROFILE, ARCH, POSITIONING, JD, resume.retrieval, provider, model="m", company="Initech"
    )
    clean = run_gates(resume.content, cover.letter, PROFILE, POSITIONING, ARCH, JD, company="Initech")
    assert all(r.passed for r in clean), [r for r in clean if not r.passed]

    bad = resume.content.model_copy(deep=True)
    corrupt(bad)
    results = run_gates(bad, cover.letter, PROFILE, POSITIONING, ARCH, JD, company="Initech")
    failed = {r.gate for r in results if not r.passed}
    assert gate in failed, f"{name}: expected {gate} to fail, failed={failed}"
