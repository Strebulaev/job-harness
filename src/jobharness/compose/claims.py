"""Atomic claims extracted from generated documents, for gate G1 (spec §13.1)."""

from __future__ import annotations

from dataclasses import dataclass

from jobharness.schemas.documents import CoverLetter, ResumeContent


@dataclass(frozen=True)
class Claim:
    text: str
    source_fact_ids: tuple[str, ...]
    location: str  # e.g. "experience[0].bullets[2]"


def extract_resume_claims(content: ResumeContent) -> list[Claim]:
    claims: list[Claim] = []
    for i, role in enumerate(content.experience):
        for j, b in enumerate(role.bullets):
            claims.append(Claim(b.text, tuple(b.source_fact_ids), f"experience[{i}].bullets[{j}]"))
    for i, proj in enumerate(content.projects):
        for j, b in enumerate(proj.bullets):
            claims.append(Claim(b.text, tuple(b.source_fact_ids), f"projects[{i}].bullets[{j}]"))
    return claims


def extract_cover_claims(letter: CoverLetter) -> list[Claim]:
    """Only sentences that cite facts are factual claims about the candidate."""
    return [
        Claim(s.text, tuple(s.source_fact_ids), f"cover.sentences[{i}]")
        for i, s in enumerate(letter.sentences)
        if s.source_fact_ids
    ]


__all__ = ["Claim", "extract_cover_claims", "extract_resume_claims"]
