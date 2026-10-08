"""Step 1.1: document schemas and fact retrieval (spec §11.4 steps 1-4)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from jobharness.compose.retrieval import MAX_SKILLS, SelectedRole, retrieve_facts, select_skills
from jobharness.schemas.archetype import Archetype, load_archetypes
from jobharness.schemas.documents import (
    CoverLetter,
    CoverSentence,
    PositioningApplied,
    ResumeBullet,
    ResumeContent,
    ResumeHeader,
    VerificationBlock,
    VerificationEntry,
)
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import Positioning, load_positioning
from jobharness.schemas.profile import Profile, Skill, load_profile

REPO_ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 8)


@pytest.fixture
def profile() -> Profile:
    return load_profile(str(REPO_ROOT / "config" / "profile.example.yaml"))


@pytest.fixture
def positioning() -> Positioning:
    return load_positioning(REPO_ROOT / "config" / "positioning.example.yaml")


@pytest.fixture
def archetype() -> Archetype:
    return load_archetypes(REPO_ROOT / "config" / "archetypes")["a_ai_llm_engineer"]


def _jd(**kw: object) -> JDParsed:
    return JDParsed.model_validate({"title": "Engineer", **kw})


def _arch(archetype: Archetype, **fact_selection: object) -> Archetype:
    data = archetype.model_dump()
    data["fact_selection"] = {**data["fact_selection"], **fact_selection}
    return Archetype.model_validate(data)


def _bullet_ids(result_role: SelectedRole) -> list[str]:
    return [b.bullet.id for b in result_role.bullets]


# ---------------------------------------------------------------- schemas
def test_resume_bullet_requires_source_fact_ids() -> None:
    with pytest.raises(ValidationError):
        ResumeBullet(text="x", source_fact_ids=[])


def test_rendered_excludes_verification_block() -> None:
    content = ResumeContent(
        header=ResumeHeader(full_name="J D", email="j@example.com", location="Kiev, UA"),
        headline="h",
        positioning_applied=PositioningApplied(
            employer_display="anonymized",
            title_display="exact",
            leadership_visibility="minimal",
            recency_window_years=10,
        ),
        verification_block=VerificationBlock(
            experience=[
                VerificationEntry(
                    experience_id="exp.acme",
                    employer_real="Acme Corp",
                    title_real="CTO",
                    start="2019-03",
                )
            ]
        ),
    )
    assert "verification_block" not in content.rendered()
    assert "Acme Corp" not in str(content.rendered())
    assert "Acme Corp" in content.model_dump_json()


def test_resume_summary_capped_at_three_lines() -> None:
    with pytest.raises(ValidationError):
        ResumeContent.model_validate(
            {
                "header": {"full_name": "a", "email": "b", "location": "c"},
                "headline": "h",
                "summary": ["1", "2", "3", "4"],
                "positioning_applied": {
                    "employer_display": "full",
                    "title_display": "exact",
                    "leadership_visibility": "full",
                    "recency_window_years": 5,
                },
            }
        )


def test_cover_letter_text_and_word_count() -> None:
    letter = CoverLetter(
        sentences=[
            CoverSentence(text="One two three.", role="observation"),
            CoverSentence(text="Four five.", role="proof", source_fact_ids=["exp.acme.b1"]),
        ]
    )
    assert letter.text == "One two three. Four five."
    assert letter.word_count == 5


# ------------------------------------------------------------- retrieval
def test_positioning_filter_hides_suppressed_kinds(
    profile: Profile, positioning: Positioning, archetype: Archetype
) -> None:
    result = retrieve_facts(profile, archetype, positioning, _jd(), today=TODAY)
    ids = {b.bullet.id for r in result.roles for b in r.bullets}
    # strategy bullets (exp.acme.b2, exp.globex.b2) are suppressed by the archetype
    assert "exp.acme.b2" not in ids and "exp.globex.b2" not in ids
    assert {"exp.acme.b1", "exp.acme.b3", "exp.globex.b1"} <= ids


def test_leadership_visibility_none_hides_leadership(
    profile: Profile, positioning: Positioning, archetype: Archetype
) -> None:
    profile.experience[0].bullets[0].kind = "leadership"
    arch = _arch(archetype, suppress_kinds=[])
    shown = retrieve_facts(
        profile, arch, positioning.model_copy(update={"leadership_visibility": "minimal"}),
        _jd(), today=TODAY,
    )
    hidden = retrieve_facts(
        profile, arch, positioning.model_copy(update={"leadership_visibility": "none"}),
        _jd(), today=TODAY,
    )
    assert "exp.acme.b1" in _bullet_ids(shown.roles[0])
    assert "exp.acme.b1" not in _bullet_ids(hidden.roles[0])


def test_jd_relevance_orders_bullets(
    profile: Profile, positioning: Positioning, archetype: Archetype
) -> None:
    arch = _arch(archetype, prefer_tags=[], suppress_kinds=[])
    result = retrieve_facts(
        profile, arch, positioning, _jd(tech_stack=["RAG", "evals"]), today=TODAY
    )
    assert _bullet_ids(result.roles[0])[0] == "exp.acme.b3"


def test_prefer_tags_boost_orders_bullets_without_jd_signal(
    profile: Profile, positioning: Positioning, archetype: Archetype
) -> None:
    arch = _arch(archetype, prefer_tags=["ai"], suppress_kinds=[])
    result = retrieve_facts(profile, arch, positioning, _jd(), today=TODAY)
    assert _bullet_ids(result.roles[0])[0] == "exp.acme.b3"


def test_recent_and_older_bullet_caps(
    profile: Profile, positioning: Positioning, archetype: Archetype
) -> None:
    arch = _arch(
        archetype, suppress_kinds=[], max_bullets_per_role={"recent": 1, "older": 1}
    )
    result = retrieve_facts(profile, arch, positioning, _jd(), today=TODAY)
    by_id = {r.experience.id: r for r in result.roles}
    assert by_id["exp.acme"].recent and len(by_id["exp.acme"].bullets) == 1
    assert not by_id["exp.globex"].recent and len(by_id["exp.globex"].bullets) == 1


def test_roles_outside_recency_window_become_earlier(
    profile: Profile, positioning: Positioning, archetype: Archetype
) -> None:
    short = positioning.model_copy(update={"recency_window_years": 5})
    result = retrieve_facts(profile, archetype, short, _jd(), today=TODAY)
    assert [r.experience.id for r in result.roles] == ["exp.acme"]
    assert [e.id for e in result.earlier_roles] == ["exp.globex"]


def test_summary_capped_and_fact_ids_cover_selection(
    profile: Profile, positioning: Positioning, archetype: Archetype
) -> None:
    result = retrieve_facts(profile, archetype, positioning, _jd(), today=TODAY)
    assert len(result.summary_facts) <= 3
    all_profile_ids = {i for ids in profile.all_fact_ids().values() for i in ids}
    assert result.fact_ids() <= all_profile_ids


def test_retrieval_is_deterministic(
    profile: Profile, positioning: Positioning, archetype: Archetype
) -> None:
    jd = _jd(must_have=["Python", "RAG"], responsibilities=["build evaluation pipelines"])
    a = retrieve_facts(profile, archetype, positioning, jd, today=TODAY)
    b = retrieve_facts(profile, archetype, positioning, jd, today=TODAY)
    assert a == b


# ---------------------------------------------------------------- skills
def test_skills_jd_required_first_and_weak_skill_gated(
    profile: Profile, archetype: Archetype
) -> None:
    no_k8s = select_skills(profile, _jd(must_have=["Python"]), archetype)
    assert "Kubernetes" not in [s.name for s in no_k8s]  # no evidence, not required
    with_k8s = select_skills(
        profile, _jd(must_have=["Kubernetes", "Python"], nice_to_have=["RAG"]), archetype
    )
    names = [s.name for s in with_k8s]
    assert "Kubernetes" in names
    # required skills come before archetype nice-to-have; "rag" is nice-to-have only
    assert names.index("Python") < names.index("RAG")
    assert names.index("Kubernetes") < names.index("RAG")


def test_skills_below_working_never_listed(profile: Profile, archetype: Archetype) -> None:
    profile.skills.append(
        Skill(id="skill.go", name="Go", level="familiar", years=1, evidence_fact_ids=[])
    )
    skills = select_skills(profile, _jd(must_have=["Go"]), archetype)
    assert "Go" not in [s.name for s in skills]


def test_skills_capped_at_twelve(profile: Profile, archetype: Archetype) -> None:
    names = [f"Tool{i}" for i in range(15)]
    profile.skills = [
        Skill(id=f"skill.t{i}", name=n, level="expert", years=5, evidence_fact_ids=[])
        for i, n in enumerate(names)
    ]
    skills = select_skills(profile, _jd(tech_stack=names), archetype)
    assert len(skills) == MAX_SKILLS == 12


def test_skill_match_is_whole_word(profile: Profile, archetype: Archetype) -> None:
    profile.skills.append(
        Skill(
            id="skill.api", name="API", level="expert", years=5, evidence_fact_ids=["exp.acme.b1"]
        )
    )
    skills = select_skills(profile, _jd(must_have=["FastAPI services"]), archetype)
    assert "API" not in [s.name for s in skills]
