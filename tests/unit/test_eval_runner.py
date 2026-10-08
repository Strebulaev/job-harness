"""Step 2.3: judges, regeneration loop and the claims suite."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jobharness.db.models import EvalRun
from jobharness.db.session import create_schema, init_session_factory, make_engine
from jobharness.eval.runner import (
    CLAIMS_MIN_RECALL,
    Models,
    compose_gated,
    evaluate_claims,
    record_eval_run,
)
from jobharness.llm.scripted_provider import ScriptedProvider
from jobharness.schemas.archetype import load_archetypes
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import load_positioning
from jobharness.schemas.profile import load_profile

ROOT = Path(__file__).resolve().parents[2]
PROFILE = load_profile(str(ROOT / "config" / "profile.example.yaml"))
POSITIONING = load_positioning(ROOT / "config" / "positioning.example.yaml")
ARCH = load_archetypes(ROOT / "config" / "archetypes")["a_ai_llm_engineer"]
JD = JDParsed(title="LLM Engineer", must_have=["Python"])
MODELS = Models(compose="m", judge="j")


def _boom(**_: object) -> dict[str, object]:
    raise RuntimeError("offline")


def _provider(relevance: int = 4, fits: list[str] | None = None) -> ScriptedProvider:
    verdicts = list(fits or ["on_target"])

    def fit(**_: object) -> dict[str, object]:
        return {"verdict": verdicts.pop(0) if len(verdicts) > 1 else verdicts[0], "rationale": "r"}

    return ScriptedProvider({
        "resume_compose": _boom,
        "cover_compose": _boom,
        "judge_resume": lambda **_: {"scores": {"relevance": relevance, "specificity": 4}, "rationale": "r"},
        "judge_cover": lambda **_: {"scores": {"personalization": 4}, "rationale": "r"},
        "fit_sound_judge": fit,
    })


async def test_gated_ok_with_judges() -> None:
    res = await compose_gated(
        PROFILE, ARCH, POSITIONING, JD, _provider(), MODELS, today=date(2026, 10, 8),
        company="Initech",
    )
    assert res.status == "ok" and res.iterations == 1
    assert res.report.judges is not None and res.report.judges.relevance == 4


async def test_two_failed_iterations_end_in_gated_fail() -> None:
    res = await compose_gated(
        PROFILE, ARCH, POSITIONING, JD, _provider(relevance=2), MODELS,
        today=date(2026, 10, 8), company="Initech", max_iterations=2,
    )
    assert res.status == "gated_fail" and res.iterations == 3
    assert any("relevance" in f for f in res.report.failures)


async def test_too_senior_reruns_once_with_handson_titles() -> None:
    exact = POSITIONING.model_copy(update={"title_display": "exact"})
    res = await compose_gated(
        PROFILE, ARCH, exact, JD, _provider(fits=["too_senior", "on_target"]), MODELS,
        today=date(2026, 10, 8), company="Initech",
    )
    assert res.iterations == 2
    assert any("hands-on" in e.title_display for e in res.resume.content.experience)


def test_claims_suite_meets_recall_floor() -> None:
    res = evaluate_claims(ROOT / "eval_data" / "golden_claims", PROFILE)
    assert res.n_fabricated >= 15 and res.n_clean >= 30
    assert res.recall >= CLAIMS_MIN_RECALL, res.missed
    assert res.false_flags == 0, res.flagged_clean


def test_eval_run_row_is_recorded(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "t.db")
    create_schema(engine)
    factory = init_session_factory(engine)
    with factory() as s:
        record_eval_run(s, "doc", 1, {"gates": []}, True)
        s.commit()
        row = s.query(EvalRun).one()
        assert row.kind == "doc" and row.passed is True
