"""Step 2.2: gates G1-G7."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from jobharness.compose.cover import compose_cover
from jobharness.compose.resume import compose_resume
from jobharness.eval.gates import (
    g1_truth,
    g2_consistency,
    g3_positioning_legal,
    g4_coverage,
    g5_format,
    g6_cover,
    g7_policy,
    run_gates,
)
from jobharness.llm.scripted_provider import ScriptedProvider
from jobharness.schemas.archetype import load_archetypes
from jobharness.schemas.documents import CoverLetter, CoverSentence, ResumeContent
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import load_positioning
from jobharness.schemas.profile import load_profile

ROOT = Path(__file__).resolve().parents[2]
PROFILE = load_profile(str(ROOT / "config" / "profile.example.yaml"))
POSITIONING = load_positioning(ROOT / "config" / "positioning.example.yaml")
ARCH = load_archetypes(ROOT / "config" / "archetypes")["a_ai_llm_engineer"]
JD = JDParsed(title="LLM Engineer", must_have=["Python", "SQL"], tech_stack=["Python"])


def _boom(**_: object) -> dict[str, object]:
    raise RuntimeError("offline")


@pytest.fixture
async def docs() -> tuple[ResumeContent, CoverLetter]:
    provider = ScriptedProvider({"resume_compose": _boom, "cover_compose": _boom})
    resume = await compose_resume(
        PROFILE, ARCH, POSITIONING, JD, provider, model="m", today=date(2026, 10, 8)
    )
    cover = await compose_cover(
        PROFILE, ARCH, POSITIONING, JD, resume.retrieval, provider, model="m", company="Initech"
    )
    return resume.content, cover.letter


def _run(content: ResumeContent, letter: CoverLetter):  # type: ignore[no-untyped-def]
    return run_gates(
        content, letter, PROFILE, POSITIONING, ARCH, JD, company="Initech"
    )


def test_clean_documents_pass_every_gate(docs) -> None:  # type: ignore[no-untyped-def]
    content, letter = docs
    results = _run(content, letter)
    assert [r.gate for r in results] == ["G1", "G2", "G3", "G4", "G5", "G6", "G7"]
    failed = {r.gate: r.messages for r in results if not r.passed}
    assert failed == {}


def test_g1_numeric_fabrication_fails(docs) -> None:  # type: ignore[no-untyped-def]
    content, letter = docs
    bad = content.model_copy(deep=True)
    bad.experience[0].bullets[0].text = bad.experience[0].bullets[0].text.replace("2M", "9M")
    bad.experience[0].bullets[0].text += " Reached 9M req/day."
    res = g1_truth(bad, letter, PROFILE, JD, "Initech")
    assert not res.passed and any("number" in m for m in res.messages)


def test_g1_unknown_fact_id_fails(docs) -> None:  # type: ignore[no-untyped-def]
    content, letter = docs
    bad = content.model_copy(deep=True)
    bad.experience[0].bullets[0].source_fact_ids = ["exp.nope.b1"]
    assert not g1_truth(bad, letter, PROFILE, JD).passed


def test_g1_llm_unsupported_label_fails(docs) -> None:  # type: ignore[no-untyped-def]
    content, letter = docs
    res = g1_truth(content, letter, PROFILE, JD, "Initech", llm_labels=["unsupported"])
    assert not res.passed


def test_g2_dates_must_match_profile_and_other_documents(docs) -> None:  # type: ignore[no-untyped-def]
    content, _ = docs
    bad = content.model_copy(deep=True)
    bad.experience[0].start = "2018-01"
    assert not g2_consistency(bad, PROFILE).passed
    assert not g2_consistency(content, PROFILE, previous=[bad]).passed
    assert g2_consistency(content, PROFILE, previous=[content]).passed


def test_g3_title_level_change_fails(docs) -> None:  # type: ignore[no-untyped-def]
    content, _ = docs
    bad = content.model_copy(deep=True)
    bad.experience[0].title_display = "VP of Engineering"
    res = g3_positioning_legal(bad, PROFILE)
    assert not res.passed and "title display" in res.messages[0]


def test_g3_anonymization_requires_permission(docs) -> None:  # type: ignore[no-untyped-def]
    content, _ = docs
    profile = PROFILE.model_copy(deep=True)
    profile.disclosure_rules.allow_employer_anonymization = False
    assert not g3_positioning_legal(content, profile).passed


def test_g4_flags_missing_supportable_requirement(docs) -> None:  # type: ignore[no-untyped-def]
    content, _ = docs
    bare = content.model_copy(update={"skills_core": []}, deep=True)
    for e in bare.experience:
        for b in e.bullets:
            b.text = "Worked on systems."
    bare.summary = []
    res = g4_coverage(bare, JD, PROFILE)
    assert not res.passed and any("missing" in m for m in res.messages)
    assert g4_coverage(content, JD, PROFILE).passed


def test_g5_three_page_pdf_fails(docs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from pypdf import PdfWriter

    content, _ = docs
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=595, height=842)
    pdf = tmp_path / "three.pdf"
    with pdf.open("wb") as f:
        writer.write(f)
    res = g5_format(content, pdf)
    assert not res.passed and any("3 pages" in m for m in res.messages)


def test_g6_rules(docs) -> None:  # type: ignore[no-untyped-def]
    _, letter = docs
    assert g6_cover(letter, ARCH, "Initech").passed
    bad = CoverLetter(sentences=[*letter.sentences, CoverSentence(text="I am a rockstar [Name].", role="style")])
    res = g6_cover(bad, ARCH, "Initech")
    assert not res.passed
    assert any("banned" in m for m in res.messages) and any("placeholder" in m for m in res.messages)
    assert not g6_cover(letter, ARCH, "Umbrella Corp").passed  # wrong company


def test_g7_never_claim_phrase_fails(docs) -> None:  # type: ignore[no-untyped-def]
    content, letter = docs
    bad = content.model_copy(deep=True)
    bad.summary = [*bad.summary, "Kubernetes certified engineer."]
    res = g7_policy(bad, letter, PROFILE, POSITIONING)
    assert not res.passed and "never_claim" in res.messages[0]
