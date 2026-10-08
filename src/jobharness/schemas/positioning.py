"""Positioning schema (spec §9): the dial between extremes the composer and
overqualification module consume."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RateExpectation(_Strict):
    min: float = Field(ge=0)
    max: float = Field(ge=0)


class HoursWeek(_Strict):
    min: float = Field(ge=0)
    max: float = Field(ge=0)


class Positioning(_Strict):
    target_level: Literal["mid", "senior_ic", "staff_ic"] = "senior_ic"
    suppress_kinds_default: list[str] = Field(default_factory=list)
    leadership_visibility: Literal["none", "minimal", "full"] = "minimal"
    recency_window_years: int = Field(ge=0, default=10)
    employer_display: Literal["full", "anonymized"] = "full"
    title_display: Literal["exact", "handson_descriptor"] = "exact"
    rate_expectation_usd_month: RateExpectation = Field(
        default_factory=lambda: RateExpectation(min=2000, max=4000)
    )
    hours_week: HoursWeek = Field(default_factory=lambda: HoursWeek(min=15, max=30))
    engagement_label: str = "Independent contractor (ICA/B2B)"


def load_positioning(path: str | Path) -> Positioning:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"positioning file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"positioning root must be a mapping: {p}")
    return Positioning.model_validate(raw)


__all__ = ["HoursWeek", "Positioning", "RateExpectation", "load_positioning"]
