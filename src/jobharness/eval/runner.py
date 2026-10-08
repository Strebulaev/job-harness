"""Eval orchestration: per-document gates + judges, the regeneration loop,
and the golden-claims suite (spec §13.3)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from jobharness.compose.claims import extract_cover_claims, extract_resume_claims
from jobharness.compose.cover import CoverResult, compose_cover
from jobharness.compose.resume import ResumeResult, compose_resume
from jobharness.db.models import EvalRun
from jobharness.eval.claims_check import check_claim, fact_index
from jobharness.eval.gates import GateResult, llm_verify_claims, run_gates
from jobharness.eval.judge import JudgeReport, run_judges
from jobharness.llm.provider import LLMProvider
from jobharness.schemas.archetype import Archetype
from jobharness.schemas.documents import CoverLetter, ResumeContent
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import Positioning
from jobharness.schemas.profile import Profile

CLAIMS_MIN_RECALL = 0.95


# ------------------------------------------------------------ per document
@dataclass
class EvalReport:
    gates: list[GateResult]
    judges: JudgeReport | None = None
    judge_error: str | None = None

    @property
    def failures(self) -> list[str]:
        out = [f"{g.gate}: {m}" for g in self.gates if not g.passed and g.blocking for m in g.messages]
        if self.judges is not None:
            out += [f"judge: {m}" for m in self.judges.blocking_failures()]
        return out

    @property
    def passed(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "gates": [
                {"gate": g.gate, "passed": g.passed, "messages": list(g.messages)} for g in self.gates
            ],
            "judges": self.judges.as_dict() if self.judges else None,
            "judge_error": self.judge_error,
            "failures": self.failures,
        }


@dataclass(frozen=True)
class Models:
    compose: str
    judge: str


@dataclass
class GatedResult:
    status: str  # "ok" | "gated_fail"
    resume: ResumeResult
    cover: CoverResult
    report: EvalReport
    pdf_path: Path | None = None
    iterations: int = 1
    history: list[str] = field(default_factory=list)


async def evaluate_document(
    content: ResumeContent,
    letter: CoverLetter | None,
    profile: Profile,
    positioning: Positioning,
    archetype: Archetype,
    jd: JDParsed,
    provider: LLMProvider,
    models: Models,
    *,
    company: str | None = None,
    pdf_path: Path | None = None,
    previous: list[ResumeContent] | None = None,
    use_llm_verify: bool = False,
    use_judges: bool = True,
    include_rate: bool = True,
) -> EvalReport:
    labels = None
    if use_llm_verify:
        claims = extract_resume_claims(content) + (extract_cover_claims(letter) if letter else [])
        try:
            labels = await llm_verify_claims(claims, profile, provider, model=models.judge)
        except Exception:
            labels = None  # secondary check only; code checks still run
    gates = run_gates(
        content, letter, profile, positioning, archetype, jd,
        company=company, pdf_path=pdf_path, previous=previous, llm_labels=labels,
        include_rate=include_rate,
    )
    judges: JudgeReport | None = None
    err: str | None = None
    if use_judges:
        try:
            judges = await run_judges(content, letter, jd, provider, model=models.judge)
        except Exception as e:
            err = str(e)[:200]
    return EvalReport(gates=gates, judges=judges, judge_error=err)


async def compose_gated(
    profile: Profile,
    archetype: Archetype,
    positioning: Positioning,
    jd: JDParsed,
    provider: LLMProvider,
    models: Models,
    *,
    today: date,
    company: str | None = None,
    render: Callable[[ResumeContent], Path | None] | None = None,
    previous: list[ResumeContent] | None = None,
    include_rate: bool = True,
    overqualified: bool = False,
    max_iterations: int = 2,
    use_llm_verify: bool = False,
    use_judges: bool = True,
) -> GatedResult:
    """Compose resume + cover, run the gates, regenerate with feedback up to
    ``max_iterations`` times (spec §11.4). ``too_senior`` triggers one re-run
    with hands-on title descriptors."""
    feedback = ""
    pos = positioning
    handson_tried = False
    history: list[str] = []
    result: GatedResult | None = None
    for it in range(1, max_iterations + 2):
        resume = await compose_resume(
            profile, archetype, pos, jd, provider, model=models.compose, today=today,
            feedback=feedback,
        )
        cover = await compose_cover(
            profile, archetype, pos, jd, resume.retrieval, provider, model=models.compose,
            company=company, include_rate=include_rate, overqualified=overqualified,
            feedback=feedback,
        )
        pdf = render(resume.content) if render else None
        report = await evaluate_document(
            resume.content, cover.letter, profile, pos, archetype, jd, provider, models,
            company=company, pdf_path=pdf, previous=previous, use_llm_verify=use_llm_verify,
            use_judges=use_judges, include_rate=include_rate,
        )
        status = "ok" if report.passed else "gated_fail"
        result = GatedResult(status, resume, cover, report, pdf, it, history)
        if report.judges and report.judges.fit == "too_senior" and not handson_tried:
            handson_tried = True
            pos = pos.model_copy(update={"title_display": "handson_descriptor"})
            history.append("fit judge: too senior; re-running with hands-on titles")
            continue
        if report.passed:
            return result
        feedback = "; ".join(report.failures)[:800]
        history.append(f"iteration {it} failed: {feedback}")
    assert result is not None
    return result


def record_eval_run(
    session: Session, kind: str, target_id: int | None, results: dict[str, object], passed: bool
) -> None:
    session.add(
        EvalRun(kind=kind, target_id=target_id, results_json=json.dumps(results, sort_keys=True),
                passed=passed)
    )


# ------------------------------------------------------------ golden claims
@dataclass
class ClaimsSuiteResult:
    n_fabricated: int
    n_clean: int
    detected: int
    false_flags: int
    missed: list[str]
    flagged_clean: list[str]

    @property
    def recall(self) -> float:
        return self.detected / self.n_fabricated if self.n_fabricated else 1.0

    @property
    def clean_pass_rate(self) -> float:
        return (self.n_clean - self.false_flags) / self.n_clean if self.n_clean else 1.0

    def as_dict(self) -> dict[str, object]:
        return {
            "suite": "claims",
            "recall": round(self.recall, 4),
            "clean_pass_rate": round(self.clean_pass_rate, 4),
            "n_fabricated": self.n_fabricated,
            "n_clean": self.n_clean,
            "missed": self.missed,
            "flagged_clean": self.flagged_clean,
        }


def evaluate_claims(golden_dir: Path, profile: Profile) -> ClaimsSuiteResult:
    index = fact_index(profile)
    detected = fabricated = clean = false_flags = 0
    missed: list[str] = []
    flagged: list[str] = []
    for path in sorted(golden_dir.glob("c*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        issues = check_claim(data["snippet"], data["cited_fact_ids"], index)
        if data["expected_label"] == "supported":
            clean += 1
            if issues:
                false_flags += 1
                flagged.append(path.name)
        else:
            fabricated += 1
            if issues:
                detected += 1
            else:
                missed.append(path.name)
    return ClaimsSuiteResult(fabricated, clean, detected, false_flags, missed, flagged)


__all__ = [
    "CLAIMS_MIN_RECALL",
    "ClaimsSuiteResult",
    "EvalReport",
    "GatedResult",
    "Models",
    "compose_gated",
    "evaluate_claims",
    "evaluate_document",
    "record_eval_run",
]
