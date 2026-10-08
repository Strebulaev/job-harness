"""Steps 1.2/1.3: resume and cover composition with a scripted provider."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from jobharness.compose.claims import extract_resume_claims
from jobharness.compose.cover import (
    MAX_WORDS,
    MIN_WORDS,
    compose_cover,
    engagement_sentence,
)
from jobharness.compose.resume import compose_resume
from jobharness.eval.claims_check import check_claim, fact_index
from jobharness.llm.scripted_provider import ScriptedProvider
from jobharness.schemas.archetype import load_archetypes
from jobharness.schemas.documents import ResumeContent
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import load_positioning
from jobharness.schemas.profile import load_profile

ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 8)
PROFILE = load_profile(str(ROOT / "config" / "profile.example.yaml"))
POSITIONING = load_positioning(ROOT / "config" / "positioning.example.yaml")
ARCH = load_archetypes(ROOT / "config" / "archetypes")["a_ai_llm_engineer"]
JD = JDParsed(
    title="LLM Engineer",
    must_have=["Python", "RAG"],
    responsibilities=["Build RAG pipelines over internal documents"],
)


def _good_resume(**_: object) -> dict[str, object]:
    return {
        "roles": [
            {"role_id": "exp.acme", "bullets": [
                {"text": "Built a RAG pipeline over internal docs, reducing support ticket volume by 25%.",
                 "source_fact_ids": ["exp.acme.b3"]},
                {"text": "Designed an event-driven ingestion pipeline handling 2M req/day.",
                 "source_fact_ids": ["exp.acme.b1"]},
            ]},
            {"role_id": "exp.globex", "bullets": [
                {"text": "Owned a payments reconciliation service processing $40M/month.",
                 "source_fact_ids": ["exp.globex.b1"]},
            ]},
        ],
        "projects": [
            {"role_id": "prj.1", "bullets": [
                {"text": "Implemented the citation-accuracy metric used by 12 downstream projects.",
                 "source_fact_ids": ["prj.1.b1"]},
            ]},
        ],
    }


async def _compose(handler):  # type: ignore[no-untyped-def]
    provider = ScriptedProvider({"resume_compose": handler})
    return await compose_resume(
        PROFILE, ARCH, POSITIONING, JD, provider, model="m", today=TODAY
    )


async def test_valid_draft_is_used_and_every_bullet_is_cited() -> None:
    res = await _compose(_good_resume)
    assert res.fallback_ids == [] and res.llm_error is None
    ids = {i for g in PROFILE.all_fact_ids().values() for i in g}
    for claim in extract_resume_claims(res.content):
        assert claim.source_fact_ids and set(claim.source_fact_ids) <= ids
    texts = [b.text for e in res.content.experience for b in e.bullets]
    assert any("RAG pipeline" in t for t in texts)


async def test_fabricated_number_triggers_retry_then_fallback() -> None:
    calls = {"n": 0}

    def bad(**_: object) -> dict[str, object]:
        calls["n"] += 1
        d = _good_resume()
        d["roles"][0]["bullets"][1]["text"] = "Designed an ingestion pipeline handling 9M req/day."  # type: ignore[index]
        return d

    res = await _compose(bad)
    assert calls["n"] == 3  # first try + 2 iterations
    assert "exp.acme" in res.fallback_ids
    originals = {b.text for e in PROFILE.experience for b in e.bullets}
    acme = next(e for e in res.content.experience if e.employer_display.startswith("B2B"))
    assert all(b.text in originals for b in acme.bullets)


async def test_new_technology_is_rejected() -> None:
    def bad(**_: object) -> dict[str, object]:
        d = _good_resume()
        d["roles"][1]["bullets"][0]["text"] = "Owned a Kafka payments reconciliation service."  # type: ignore[index]
        return d

    res = await _compose(bad)
    assert "exp.globex" in res.fallback_ids


async def test_provider_failure_falls_back_to_verbatim_bullets() -> None:
    def boom(**_: object) -> dict[str, object]:
        raise RuntimeError("provider down")

    res = await _compose(boom)
    assert res.llm_error == "provider down" and res.fallback_ids
    index = fact_index(PROFILE)
    for claim in extract_resume_claims(res.content):
        assert check_claim(claim.text, list(claim.source_fact_ids), index) == []


async def test_deterministic_and_verification_block_not_rendered() -> None:
    a = await _compose(_good_resume)
    b = await _compose(_good_resume)
    assert a.content.model_dump_json() == b.content.model_dump_json()
    assert isinstance(a.content, ResumeContent)
    rendered = str(a.content.rendered())
    assert "Acme Corp" not in rendered  # anonymized in the rendered fields
    assert "Acme Corp" in a.content.model_dump_json()  # real values stored
    assert a.content.positioning_applied.employer_display == "anonymized"


# ----------------------------------------------------------------- cover
async def _cover(handler, **kw):  # type: ignore[no-untyped-def]
    resume = await _compose(_good_resume)
    provider = ScriptedProvider({"cover_compose": handler})
    return await compose_cover(
        PROFILE, ARCH, POSITIONING, JD, resume.retrieval, provider,
        model="m", company="Initech", **kw,
    )


def _good_cover(**_: object) -> dict[str, object]:
    return {
        "observation": "Your LLM Engineer role at Initech centres on building RAG pipelines over internal documents.",
        "proof": "I built a RAG pipeline over internal docs that reduced support ticket volume by 25%.",
        "proof_fact_ids": ["exp.acme.b3"],
        "closing": "I would welcome a conversation about how I can help.",
    }


async def test_cover_letter_rules() -> None:
    res = await _cover(_good_cover)
    assert not res.used_fallback, res.problems
    letter = res.letter
    assert MIN_WORDS <= letter.word_count <= MAX_WORDS
    assert any(s.role == "format" for s in letter.sentences)
    assert engagement_sentence(POSITIONING) in letter.text
    low = letter.text.lower()
    assert "passionate" not in low and "[" not in letter.text and "{{" not in letter.text
    assert all(s.source_fact_ids for s in letter.sentences if s.role == "proof")


async def test_overqualified_adds_exactly_one_rationale_sentence() -> None:
    plain = await _cover(_good_cover)
    over = await _cover(_good_cover, overqualified=True)
    n = lambda r: sum(1 for s in r.letter.sentences if s.role == "rationale")  # noqa: E731
    assert n(plain) == 0 and n(over) == 1


async def test_banned_phrase_forces_fallback() -> None:
    def bad(**_: object) -> dict[str, object]:
        d = _good_cover()
        d["closing"] = "I am passionate about this and would love to talk."
        return d

    res = await _cover(bad)
    assert res.used_fallback
    assert "passionate" not in res.letter.text.lower()
    assert MIN_WORDS <= res.letter.word_count <= MAX_WORDS


async def test_invented_proof_number_is_rejected() -> None:
    def bad(**_: object) -> dict[str, object]:
        d = _good_cover()
        d["proof"] = "I built a RAG pipeline that cut support tickets by 80%."
        return d

    res = await _cover(bad)
    assert res.used_fallback


@pytest.mark.parametrize("include_rate", [True, False])
def test_engagement_sentence_rate_toggle(include_rate: bool) -> None:
    s = engagement_sentence(POSITIONING, include_rate)
    assert ("rate expectation" in s) is include_rate
    assert "independent contractor" in s
