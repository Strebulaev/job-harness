"""Step 1.5: M4 acceptance across all six archetypes (offline)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from jobharness.compose.claims import extract_resume_claims
from jobharness.compose.cover import MAX_WORDS, MIN_WORDS, compose_cover
from jobharness.compose.resume import compose_resume
from jobharness.eval.claims_check import check_claim, fact_index
from jobharness.llm.scripted_provider import ScriptedProvider
from jobharness.render.typst_renderer import render_resume, typst_available
from jobharness.schemas.archetype import load_archetypes
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import load_positioning
from jobharness.schemas.profile import load_profile

ROOT = Path(__file__).resolve().parents[2]
ARCHETYPES = load_archetypes(ROOT / "config" / "archetypes")
PROFILE = load_profile(str(ROOT / "config" / "profile.example.yaml"))
POSITIONING = load_positioning(ROOT / "config" / "positioning.example.yaml")
TODAY = date(2026, 10, 8)
JD = JDParsed(
    title="Backend Engineer",
    must_have=["Python", "SQL"],
    tech_stack=["Python", "PostgreSQL"],
    responsibilities=["Build reliable data pipelines"],
)


def _offline_provider() -> ScriptedProvider:
    def boom(**_: object) -> dict[str, object]:
        raise RuntimeError("offline")

    return ScriptedProvider({"resume_compose": boom, "cover_compose": boom})


@pytest.mark.parametrize("archetype_id", sorted(ARCHETYPES))
async def test_archetype_end_to_end(archetype_id: str, tmp_path: Path) -> None:
    arch = ARCHETYPES[archetype_id]
    provider = _offline_provider()
    resume = await compose_resume(
        PROFILE, arch, POSITIONING, JD, provider, model="m", today=TODAY
    )
    again = await compose_resume(
        PROFILE, arch, POSITIONING, JD, provider, model="m", today=TODAY
    )
    assert resume.content.model_dump_json() == again.content.model_dump_json()

    index = fact_index(PROFILE)
    claims = extract_resume_claims(resume.content)
    assert claims
    for c in claims:
        assert check_claim(c.text, list(c.source_fact_ids), index) == []

    cover = await compose_cover(
        PROFILE, arch, POSITIONING, JD, resume.retrieval, provider, model="m", company="Initech"
    )
    assert MIN_WORDS <= cover.letter.word_count <= MAX_WORDS

    if typst_available():
        from pypdf import PdfReader

        a = render_resume(resume.content, tmp_path / "a", "r")
        b = render_resume(again.content, tmp_path / "b", "r")
        assert 1 <= len(PdfReader(str(a.pdf)).pages) <= 2
        assert a.pdf.read_bytes() == b.pdf.read_bytes()
