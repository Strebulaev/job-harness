"""Archetype schema (spec §8). Archetypes are data-driven: adding a new one
must not require code changes."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaxBulletsPerRole(_Strict):
    recent: int = Field(ge=1)
    older: int = Field(ge=0)


class FactSelection(_Strict):
    prefer_tags: list[str] = Field(default_factory=list)
    suppress_kinds: list[str] = Field(default_factory=list)
    max_bullets_per_role: MaxBulletsPerRole = Field(
        default_factory=lambda: MaxBulletsPerRole(recent=5, older=2)
    )


class CoverLetterConfig(_Strict):
    proof_points_tags: list[str] = Field(default_factory=list)
    avoid_phrases: list[str] = Field(default_factory=list)


class RateGuidance(_Strict):
    min: float = Field(ge=0)
    max: float = Field(ge=0)


class Archetype(_Strict):
    id: str
    name: str
    headline_templates: list[str]
    must_have_keywords: list[str] = Field(default_factory=list)
    nice_to_have_keywords: list[str] = Field(default_factory=list)
    jd_match_signals: list[str] = Field(default_factory=list)
    fact_selection: FactSelection = Field(default_factory=FactSelection)
    cover_letter: CoverLetterConfig = Field(default_factory=CoverLetterConfig)
    rate_guidance_usd_month: RateGuidance | None = None
    typical_hours_week: tuple[float, float] | list[float] | None = None

    def __init__(self, **data: object) -> None:
        hours = data.get("typical_hours_week")
        if isinstance(hours, list):
            data["typical_hours_week"] = (float(hours[0]), float(hours[1]))
        super().__init__(**data)


def load_archetypes(directory: str | Path) -> dict[str, Archetype]:
    """Load every ``*.yaml`` in ``directory``, keyed by archetype id."""
    out: dict[str, Archetype] = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"archetype file root must be a mapping: {path}")
        arch = Archetype.model_validate(raw)
        out[arch.id] = arch
    return out


__all__ = [
    "Archetype",
    "CoverLetterConfig",
    "FactSelection",
    "MaxBulletsPerRole",
    "RateGuidance",
    "load_archetypes",
]
