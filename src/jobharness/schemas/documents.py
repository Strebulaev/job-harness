"""Generated-document schemas (spec §11.4): ``ResumeContent`` and ``CoverLetter``.

Every factual statement carries ``source_fact_ids`` so gate G1 can trace it to
the profile. The real employer/title/dates live in ``verification_block`` and
are stored with the document but never rendered (use :meth:`ResumeContent.rendered`).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResumeHeader(_Strict):
    full_name: str
    email: str
    phone: str | None = None
    location: str
    links: dict[str, str] = Field(default_factory=dict)


class ResumeBullet(_Strict):
    text: str
    source_fact_ids: list[str] = Field(min_length=1)


class ResumeExperience(_Strict):
    employer_display: str
    title_display: str
    start: str
    end: str | None = None
    bullets: list[ResumeBullet] = Field(default_factory=list)


class ResumeEducation(_Strict):
    institution: str
    degree: str
    field: str
    start: str
    end: str | None = None
    source_fact_id: str


class ResumeCertification(_Strict):
    name: str
    issuer: str
    date: str
    source_fact_id: str


class ResumeProject(_Strict):
    name: str
    url: str | None = None
    bullets: list[ResumeBullet] = Field(default_factory=list)


class ResumeLanguage(_Strict):
    lang: str
    level: str


class PositioningApplied(_Strict):
    employer_display: Literal["full", "anonymized"]
    title_display: Literal["exact", "handson_descriptor"]
    leadership_visibility: Literal["none", "minimal", "full"]
    recency_window_years: int


class VerificationEntry(_Strict):
    """Real values behind one displayed experience entry (unrendered)."""

    experience_id: str
    employer_real: str
    title_real: str
    start: str
    end: str | None = None


class VerificationBlock(_Strict):
    experience: list[VerificationEntry] = Field(default_factory=list)


class ResumeContent(_Strict):
    header: ResumeHeader
    headline: str
    summary: list[str] = Field(default_factory=list, max_length=3)
    skills_core: list[str] = Field(default_factory=list, max_length=12)
    experience: list[ResumeExperience] = Field(default_factory=list)
    earlier_experience_line: str | None = None
    education: list[ResumeEducation] = Field(default_factory=list)
    certifications: list[ResumeCertification] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)
    languages: list[ResumeLanguage] = Field(default_factory=list)
    positioning_applied: PositioningApplied
    verification_block: VerificationBlock = Field(default_factory=VerificationBlock)

    def rendered(self) -> dict[str, Any]:
        """Fields safe to render: everything except the verification block."""
        return self.model_dump(mode="json", exclude={"verification_block"})


CoverRole = Literal["observation", "proof", "format", "rationale", "cta", "style"]


class CoverSentence(_Strict):
    text: str
    role: CoverRole
    source_fact_ids: list[str] = Field(default_factory=list)


class CoverLetter(_Strict):
    """Cover letter as ordered sentences; ``source_fact_ids`` are internal."""

    sentences: list[CoverSentence] = Field(min_length=1)

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.sentences)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


class BulletDraft(_Strict):
    text: str
    source_fact_ids: list[str] = Field(default_factory=list)


class RoleDraft(_Strict):
    role_id: str
    bullets: list[BulletDraft] = Field(default_factory=list)


class ResumeDraft(_Strict):
    """LLM output of the ``resume_compose`` prompt (rewritten bullets only)."""

    roles: list[RoleDraft] = Field(default_factory=list)
    projects: list[RoleDraft] = Field(default_factory=list)


class CoverDraft(_Strict):
    """LLM output of the ``cover_compose`` prompt (the free-text parts)."""

    observation: str
    proof: str
    proof_fact_ids: list[str] = Field(default_factory=list)
    closing: str


__all__ = [
    "BulletDraft",
    "CoverDraft",
    "CoverLetter",
    "ResumeDraft",
    "RoleDraft",
    "CoverRole",
    "CoverSentence",
    "PositioningApplied",
    "ResumeBullet",
    "ResumeCertification",
    "ResumeContent",
    "ResumeEducation",
    "ResumeExperience",
    "ResumeHeader",
    "ResumeLanguage",
    "ResumeProject",
    "VerificationBlock",
    "VerificationEntry",
]
