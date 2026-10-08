"""Overqualification module (spec §9).

``gap = principal_level - posting_level`` on a 1-5 ordinal. When
``gap >= 2`` the composer runs in ``handson_focus`` mode: the cover letter
carries one format-rationale sentence and leadership visibility is lowered.
All adjustments are recorded in ``positioning_applied`` so the document is
reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jobharness.schemas.jd import Seniority
from jobharness.schemas.positioning import Positioning

#: Ordinal scale (spec §9: "levels from parsed JD: seniority and comp band
#: mapped to an ordinal 1-5").
LEVEL_ORDINAL: dict[str, int] = {
    "intern": 1,
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "lead": 4,
    "staff": 4,
    "principal": 5,
    "unknown": 3,  # neutral: treat unknown postings as mid-market
}

_PRINCIPAL_ORDINAL: dict[str, int] = {
    "mid": 2,
    "senior_ic": 3,
    "staff_ic": 4,
}


@dataclass(slots=True)
class Overqualification:
    """Result of the overqualification check for one posting."""

    principal_level: str
    posting_level: str
    gap: int
    handson_focus: bool
    notes: list[str] = field(default_factory=list)

    def positioning_applied(self) -> dict[str, object]:
        """The block that lands in ``documents.content_json.positioning_applied``."""
        return {
            "overqualification": {
                "principal_level": self.principal_level,
                "posting_level": self.posting_level,
                "gap": self.gap,
                "handson_focus": self.handson_focus,
            }
        }


def principal_ordinal(positioning: Positioning) -> int:
    return _PRINCIPAL_ORDINAL[positioning.target_level]


def posting_ordinal(seniority: Seniority) -> int:
    return LEVEL_ORDINAL.get(seniority, LEVEL_ORDINAL["unknown"])


def evaluate(
    positioning: Positioning, parsed_level: Seniority | None = None
) -> Overqualification:
    """Compute the gap and the resulting composer mode."""
    p_level = positioning.target_level
    posting_level = parsed_level or "unknown"
    gap = principal_ordinal(positioning) - posting_ordinal(posting_level)
    handson = gap >= 2
    notes: list[str] = []
    if handson:
        notes.append(
            f"gap={gap} >= 2: composer mode handson_focus; "
            "one-sentence format rationale in cover letter; lowered leadership visibility"
        )
    else:
        notes.append(f"gap={gap}: standard composer mode")
    return Overqualification(
        principal_level=p_level,
        posting_level=posting_level,
        gap=gap,
        handson_focus=handson,
        notes=notes,
    )


__all__ = [
    "LEVEL_ORDINAL",
    "Overqualification",
    "evaluate",
    "principal_ordinal",
    "posting_ordinal",
]
