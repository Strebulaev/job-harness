"""Parsed JD schema (spec §10) + compensation normalization types.

``JDParsed`` is the Pydantic model the ``jd_parse`` prompt's structured output
must validate against. The parser post-check (spec §10) downgrades any
non-"unknown" categorical field whose ``evidence_spans`` entry is not a
substring of ``jd_raw`` to ``"unknown"``.

Categorical fields that the post-check enforces are listed in
``EVIDENCE_CATEGORIES``. Evidence spans are verbatim snippets; every non-
"unknown" value in this set SHOULD carry a span.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Seniority = Literal[
    "intern", "junior", "mid", "senior", "staff", "principal", "lead", "unknown"
]
EngagementType = Literal["employee", "contractor", "b2b", "freelance", "project", "unknown"]
Exclusivity = Literal["required", "preferred", "none", "unknown"]
RemotePolicy = Literal["remote", "hybrid", "onsite", "unknown"]
AIOrSubPolicy = Literal["allowed", "forbidden", "unknown"]
ApplicationMethod = Literal["email", "platform", "form", "unknown"]

#: Fields the evidence-span post-check enforces (spec §10).
EVIDENCE_CATEGORIES: tuple[str, ...] = (
    "seniority",
    "engagement_type",
    "exclusivity",
    "remote_policy",
    "onsite_required",
    "countries_allowed",
    "timezone_requirements",
    "required_overlap",
    "hours_per_week",
    "compensation",
    "must_have",
    "nice_to_have",
    "tech_stack",
    "responsibilities",
    "ai_tools_policy",
    "subcontracting_policy",
    "red_flags",
    "application_method",
)


class Compensation(BaseModel):
    """Raw compensation as parsed from the JD (before USD/month normalization).

    ``period`` is the period the source JD states; normalization to
    USD/month happens in ``parse/normalizers.py``.
    """

    model_config = ConfigDict(extra="forbid")
    min: float
    max: float
    currency: str
    period: Literal["hour", "month", "year", "project"]


class JDParsed(BaseModel):
    """Structured, post-verified parse of a raw JD (spec §10)."""

    model_config = ConfigDict(extra="forbid")

    title: str
    company: str | None = None
    seniority: Seniority = "unknown"
    engagement_type: EngagementType = "unknown"
    exclusivity: Exclusivity = "unknown"
    remote_policy: RemotePolicy = "unknown"
    onsite_required: bool | None = None
    countries_allowed: list[str] = Field(
        default_factory=list
    )  # ISO-3166 alpha-2; empty = unrestricted
    timezone_requirements: str | None = None  # verbatim snippet
    required_overlap: dict[str, str] | None = None  # {"tz","start","end"}
    hours_per_week: tuple[float, float] | None = None
    compensation: Compensation | None = None
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    ai_tools_policy: AIOrSubPolicy = "unknown"
    subcontracting_policy: AIOrSubPolicy = "unknown"
    red_flags: list[str] = Field(default_factory=list)
    application_method: ApplicationMethod = "unknown"
    application_email: str | None = None
    evidence_spans: dict[str, str] = Field(default_factory=dict)

__all__ = [
    "AIOrSubPolicy",
    "ApplicationMethod",
    "Compensation",
    "EVIDENCE_CATEGORIES",
    "EngagementType",
    "Exclusivity",
    "JDParsed",
    "RemotePolicy",
    "Seniority",
]
