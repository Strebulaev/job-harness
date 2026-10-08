"""LLM judges (spec §13.2): non-blocking scores stored with the eval run.

Blocking thresholds are configurable; the defaults block below 3/5 for
relevance and when the candidate is judged too junior. ``too_senior`` triggers
one re-composition with the hands-on title descriptors (handled by the caller).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from jobharness.llm.prompt_versions import default_version
from jobharness.llm.prompts import load_system_prompt
from jobharness.llm.provider import LLMProvider
from jobharness.render.typst_renderer import resume_to_text
from jobharness.schemas.documents import CoverLetter, ResumeContent
from jobharness.schemas.evals import FitJudgement, JudgeScores
from jobharness.schemas.jd import JDParsed

BLOCK_BELOW = 3


@dataclass(frozen=True)
class JudgeReport:
    relevance: int | None = None
    specificity: int | None = None
    personalization: int | None = None
    fit: str | None = None  # too_senior | on_target | too_junior
    rationale: str = ""

    def blocking_failures(self, block_below: int = BLOCK_BELOW) -> list[str]:
        out: list[str] = []
        if self.relevance is not None and self.relevance < block_below:
            out.append(f"relevance {self.relevance}/5")
        if self.fit == "too_junior":
            out.append("fit: too junior")
        return out

    def as_dict(self) -> dict[str, object]:
        return {
            "relevance": self.relevance, "specificity": self.specificity,
            "personalization": self.personalization, "fit": self.fit,
            "rationale": self.rationale,
        }


def _job_text(jd: JDParsed) -> str:
    return json.dumps(
        {"title": jd.title, "must_have": jd.must_have, "tech_stack": jd.tech_stack,
         "responsibilities": jd.responsibilities, "seniority": jd.seniority},
        ensure_ascii=False,
    )


async def _scores(
    provider: LLMProvider, purpose: str, model: str, user: str
) -> JudgeScores:
    out, _ = await provider.generate_structured(
        purpose=purpose, model=model,
        system=load_system_prompt(purpose, default_version(purpose)), user=user,
        schema=JudgeScores, temperature=0.0, max_tokens=400,
        prompt_version=default_version(purpose),
    )
    assert isinstance(out, JudgeScores)
    return out


def _clamp(v: int | None) -> int | None:
    return None if v is None else max(1, min(5, v))


async def run_judges(
    content: ResumeContent,
    letter: CoverLetter | None,
    jd: JDParsed,
    provider: LLMProvider,
    *,
    model: str,
) -> JudgeReport:
    job = _job_text(jd)
    r = await _scores(provider, "judge_resume", model,
                      f"JOB:\n{job}\n\nRESUME:\n{resume_to_text(content)}")
    personalization = None
    if letter is not None:
        c = await _scores(provider, "judge_cover", model, f"JOB:\n{job}\n\nLETTER:\n{letter.text}")
        personalization = _clamp(c.scores.get("personalization"))
    fit, _ = await provider.generate_structured(
        purpose="fit_sound_judge", model=model,
        system=load_system_prompt("fit_sound_judge", default_version("fit_sound_judge")),
        user=f"CANDIDATE:\n{content.headline}\n{chr(10).join(content.summary)}\n\nJOB:\n{job}",
        schema=FitJudgement, temperature=0.0, max_tokens=300,
        prompt_version=default_version("fit_sound_judge"),
    )
    assert isinstance(fit, FitJudgement)
    return JudgeReport(
        relevance=_clamp(r.scores.get("relevance")),
        specificity=_clamp(r.scores.get("specificity")),
        personalization=personalization,
        fit=fit.verdict,
        rationale=r.rationale[:300],
    )


__all__ = ["BLOCK_BELOW", "JudgeReport", "run_judges"]
