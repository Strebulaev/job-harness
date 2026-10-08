"""Structured outputs of the eval prompts (claims_verify, judges)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


ClaimLabel = Literal["supported", "partial", "unsupported"]


class ClaimVerdict(_Strict):
    index: int
    label: ClaimLabel


class ClaimsVerifyOutput(_Strict):
    labels: list[ClaimVerdict] = Field(default_factory=list)


class JudgeScores(_Strict):
    scores: dict[str, int]
    rationale: str = ""


class FitJudgement(_Strict):
    verdict: Literal["too_senior", "on_target", "too_junior"]
    rationale: str = ""


__all__ = ["ClaimLabel", "ClaimVerdict", "ClaimsVerifyOutput", "FitJudgement", "JudgeScores"]
