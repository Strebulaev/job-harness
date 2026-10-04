"""Profile schema — the single source of truth for every document (spec §7).

Every leaf fact that may appear in a document has a stable ``fact_id``.
Validation errors are fatal at load time; cross-reference and overlap checks
run in :func:`validate_profile` (invoked by ``jh profile validate``).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _month_year_to_date(value: str) -> date:
    """Parse a 'YYYY-MM' string to a date on the 1st. Raises ValueError on bad input."""
    if len(value) != 7 or value[4] != "-":
        raise ValueError(f"expected YYYY-MM, got {value!r}")
    year = int(value[0:4])
    month = int(value[5:7])
    if not 1 <= month <= 12:
        raise ValueError(f"invalid month in {value!r}")
    return date(year, month, 1)


def _validate_month_year(v: str) -> str:
    _month_year_to_date(v)  # raises on bad input
    return v


class Language(_Strict):
    lang: str
    level: str


class Links(_Strict):
    github: str | None = None
    linkedin: str | None = None
    site: str | None = None


class Location(_Strict):
    city: str
    country: str
    timezone: str


class Identity(_Strict):
    full_name: str
    public_alias: str | None = None
    email: str
    phone: str | None = None
    location: Location
    links: Links = Field(default_factory=Links)
    languages: list[Language] = Field(default_factory=list)


class SummaryFact(_Strict):
    id: str
    text: str
    tags: list[str] = Field(default_factory=list)


class Metrics(_Strict):
    name: str
    value: float


class Bullet(_Strict):
    id: str
    text: str
    tags: list[str] = Field(default_factory=list)
    kind: Literal["hands_on", "leadership", "strategy", "budget"] = "hands_on"
    metrics: list[Metrics] = Field(default_factory=list)
    evidence: str | None = None


class DisplayOptions(_Strict):
    full: str
    anonymized: str | None = None


class TitleDisplayOptions(_Strict):
    exact: str
    handson_descriptor: str | None = None


class Experience(_Strict):
    id: str
    employer_real: str
    employer_display_options: DisplayOptions
    title_real: str
    title_display_options: TitleDisplayOptions
    start: str
    end: str | None = None
    employment_type: Literal["full_time", "part_time", "contractor", "b2b", "intern"]
    concurrent: bool = False
    bullets: list[Bullet] = Field(default_factory=list)

    @field_validator("start", "end")
    @classmethod
    def _check_month_year(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is None:
            return None
        _validate_month_year(v)
        return v

    @model_validator(mode="after")
    def _order(self) -> Experience:
        s = _month_year_to_date(self.start)
        if self.end is not None:
            e = _month_year_to_date(self.end)
            if e < s:
                raise ValueError(
                    f"experience {self.id!r}: end {self.end} before start {self.start}"
                )
        return self


class Education(_Strict):
    id: str
    institution: str
    degree: str
    field: str
    start: str
    end: str | None = None

    @field_validator("start", "end")
    @classmethod
    def _check_month_year(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is None:
            return None
        _validate_month_year(v)
        return v


class Certification(_Strict):
    id: str
    name: str
    issuer: str
    date: str

    @field_validator("date")
    @classmethod
    def _check_date(cls, v: str) -> str:
        _validate_month_year(v)
        return v


class Project(_Strict):
    id: str
    name: str
    url: str | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    bullets: list[Bullet] = Field(default_factory=list)


class Skill(_Strict):
    id: str
    name: str
    level: Literal["familiar", "working", "proficient", "expert"]
    years: float = Field(ge=0)
    last_used: str | None = None
    evidence_fact_ids: list[str] = Field(default_factory=list)


class DisclosureRules(_Strict):
    allow_employer_anonymization: bool = False
    must_disclose_real_employer_on: list[str] = Field(default_factory=list)
    never_claim: list[str] = Field(default_factory=list)


class Profile(_Strict):
    version: int
    identity: Identity
    summary_facts: list[SummaryFact] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    disclosure_rules: DisclosureRules = Field(default_factory=DisclosureRules)

    # ------------------------------------------------------------------ ids
    def all_fact_ids(self) -> dict[str, list[str]]:
        """Return every fact id grouped by category, for cross-reference checks."""
        groups: dict[str, list[str]] = {
            "summary_facts": [s.id for s in self.summary_facts],
            "experience": [e.id for e in self.experience],
            "bullets": [b.id for e in self.experience for b in e.bullets],
            "education": [e.id for e in self.education],
            "certifications": [c.id for c in self.certifications],
            "projects": [p.id for p in self.projects],
            "project_bullets": [b.id for p in self.projects for b in p.bullets],
            "skills": [s.id for s in self.skills],
        }
        return groups

    def bullet_ids(self) -> set[str]:
        return {b.id for e in self.experience for b in e.bullets} | {
            b.id for p in self.projects for b in p.bullets
        }


class ProfileValidationError(Exception):
    """Raised when ``jh profile validate`` finds a fatal problem."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _overlaps(
    a_start: date, a_end: date, b_start: date, b_end: date
) -> bool:
    return a_start <= b_end and b_start <= a_end


def validate_profile(profile: Profile) -> list[str]:
    """Return a list of fatal problems (empty = valid).

    Checks (spec §7):
    - every fact id unique across the whole profile
    - date ordering within each experience (also enforced by Pydantic)
    - no overlapping full-time roles unless flagged ``concurrent: true``
    - every referenced id (skill.evidence_fact_ids) exists
    - anonymized descriptor present when ``allow_employer_anonymization``
    """
    errors: list[str] = []

    # 1. uniqueness of every fact id
    seen: dict[str, str] = {}
    for category, ids in profile.all_fact_ids().items():
        for fid in ids:
            if fid in seen:
                errors.append(
                    f"duplicate fact id {fid!r} in {seen[fid]!r} and {category!r}"
                )
            else:
                seen[fid] = category

    # 2. overlapping full-time roles
    ft = [e for e in profile.experience if e.employment_type == "full_time"]
    for i, a in enumerate(ft):
        a_s = _month_year_to_date(a.start)
        a_e = _month_year_to_date(a.end) if a.end else a_s
        for b in ft[i + 1 :]:
            b_s = _month_year_to_date(b.start)
            b_e = _month_year_to_date(b.end) if b.end else b_s
            if _overlaps(a_s, a_e, b_s, b_e) and not (a.concurrent or b.concurrent):
                errors.append(
                    f"overlapping full-time roles {a.id!r} and {b.id!r} "
                    "without concurrent: true"
                )

    # 3. skill.evidence_fact_ids must exist
    valid_ids = set(seen.keys())
    for skill in profile.skills:
        for ref in skill.evidence_fact_ids:
            if ref not in valid_ids:
                errors.append(f"skill {skill.id!r} references unknown fact id {ref!r}")

    # 4. anonymized descriptor when allowed
    if profile.disclosure_rules.allow_employer_anonymization:
        for e in profile.experience:
            if not e.employer_display_options.anonymized:
                errors.append(
                    f"experience {e.id!r}: anonymized descriptor missing but "
                    "allow_employer_anonymization is true"
                )

    return errors


def lint_profile(profile: Profile) -> list[str]:
    """Return non-fatal warnings (spec §7: unverifiable metrics, weak skills)."""
    warnings: list[str] = []

    # bullets with metrics but no evidence
    for e in profile.experience:
        for b in e.bullets:
            if b.metrics and not b.evidence:
                warnings.append(
                    f"bullet {b.id!r}: has metrics but no evidence "
                    "(unverifiable — add an `evidence` note)"
                )
    for p in profile.projects:
        for b in p.bullets:
            if b.metrics and not b.evidence:
                warnings.append(
                    f"project bullet {b.id!r}: has metrics but no evidence"
                )

    # skills without evidence
    valid_bullet_ids = profile.bullet_ids()
    for s in profile.skills:
        if not s.evidence_fact_ids:
            warnings.append(
                f"skill {s.id!r} (level={s.level}) has no evidence_fact_ids — "
                "flagged `weak`; not listed in core skills unless the JD requires it "
                "and level >= working"
            )
        for ref in s.evidence_fact_ids:
            if ref not in valid_bullet_ids:
                warnings.append(
                    f"skill {s.id!r} evidence_fact_id {ref!r} is not a bullet id"
                )

    return warnings


def load_profile(path: str) -> Profile:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ProfileValidationError([f"profile root must be a mapping: {path}"])
    return Profile.model_validate(raw)
