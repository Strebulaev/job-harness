"""Blocking gates G1-G7 (spec §13.1). Deterministic except G1's optional LLM check."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jobharness.compose.claims import Claim, extract_cover_claims, extract_resume_claims
from jobharness.compose.cover import banned_phrases, engagement_sentence
from jobharness.compose.retrieval import _matches  # whole-word skill matching
from jobharness.eval.claims_check import check_claim, fact_index
from jobharness.llm.prompt_versions import default_version
from jobharness.llm.prompts import load_system_prompt
from jobharness.llm.provider import LLMProvider
from jobharness.render.typst_renderer import resume_to_text
from jobharness.schemas.archetype import Archetype
from jobharness.schemas.documents import CoverLetter, ResumeContent
from jobharness.schemas.evals import ClaimLabel, ClaimsVerifyOutput
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import Positioning
from jobharness.schemas.profile import Profile

COVERAGE_THRESHOLD = 0.70
MIN_RESUME_WORDS, MAX_RESUME_WORDS = 100, 1000
_PLACEHOLDER = re.compile(r"\[[^\]\n]+\]|\{\{|\}\}|\bTODO\b|lorem ipsum", re.IGNORECASE)
_HEADINGS = ("EXPERIENCE", "EDUCATION", "SKILLS")


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    messages: tuple[str, ...] = ()
    blocking: bool = True


def _job_texts(jd: JDParsed, company: str | None) -> list[str]:
    return [jd.title, company or "", *jd.must_have, *jd.tech_stack, *jd.responsibilities]


# ------------------------------------------------------------------ G1
def g1_truth(
    content: ResumeContent,
    letter: CoverLetter | None,
    profile: Profile,
    jd: JDParsed,
    company: str | None = None,
    llm_labels: list[ClaimLabel] | None = None,
) -> GateResult:
    """(a) cited ids exist, (b) numbers/entities supported, (c) optional LLM labels."""
    index = fact_index(profile)
    msgs: list[str] = []
    summaries = {s.text for s in profile.summary_facts}
    for line in content.summary:
        if line not in summaries:
            msgs.append(f"summary line is not a profile summary fact: {line[:60]!r}")
    claims: list[Claim] = extract_resume_claims(content)
    for c in claims:
        for issue in check_claim(c.text, list(c.source_fact_ids), index):
            msgs.append(f"{c.location}: {issue}")
    if letter is not None:
        job_texts = _job_texts(jd, company)
        for c in extract_cover_claims(letter):
            for issue in check_claim(c.text, list(c.source_fact_ids), index, job_texts):
                msgs.append(f"{c.location}: {issue}")
    warn: list[str] = []
    if llm_labels is not None:
        for i, label in enumerate(llm_labels):
            if label == "unsupported":
                msgs.append(f"LLM verifier: claim {i} unsupported")
            elif label == "partial":
                warn.append(f"LLM verifier: claim {i} only partially supported")
    return GateResult("G1", not msgs, tuple(msgs + warn))


async def llm_verify_claims(
    claims: list[Claim], profile: Profile, provider: LLMProvider, *, model: str
) -> list[ClaimLabel]:
    """Secondary per-claim check (G1c). Unknown/missing verdicts default to supported
    only when the code checks already passed; callers treat provider errors as skip."""
    index = fact_index(profile)
    lines = []
    for i, c in enumerate(claims):
        facts = "; ".join(index[f].text for f in c.source_fact_ids if f in index)
        lines.append(f"CLAIM {i}: {c.text}\nFACTS: {facts}")
    out, _ = await provider.generate_structured(
        purpose="claims_verify",
        model=model,
        system=load_system_prompt("claims_verify", default_version("claims_verify")),
        user="\n\n".join(lines),
        schema=ClaimsVerifyOutput,
        temperature=0.0,
        max_tokens=1024,
        prompt_version=default_version("claims_verify"),
    )
    assert isinstance(out, ClaimsVerifyOutput)
    by_index = {v.index: v.label for v in out.labels}
    return [by_index.get(i, "supported") for i in range(len(claims))]


# ------------------------------------------------------------------ G2
def g2_consistency(
    content: ResumeContent, profile: Profile, previous: list[ResumeContent] | None = None
) -> GateResult:
    msgs: list[str] = []
    exps = {e.id: e for e in profile.experience}
    entries = content.verification_block.experience
    if len(entries) != len(content.experience):
        msgs.append("verification block does not match experience entries")
    for shown, ver in zip(content.experience, entries, strict=False):
        real = exps.get(ver.experience_id)
        if real is None:
            msgs.append(f"unknown experience id {ver.experience_id!r}")
            continue
        if (shown.start, shown.end) != (real.start, real.end):
            msgs.append(f"{ver.experience_id}: dates differ from profile")
    seen: dict[str, tuple[str, str | None]] = {}
    for doc in [*(previous or []), content]:
        for shown, ver in zip(doc.experience, doc.verification_block.experience, strict=False):
            key = ver.experience_id
            dates = (shown.start, shown.end)
            if key in seen and seen[key] != dates:
                msgs.append(f"{key}: dates differ across documents")
            seen.setdefault(key, dates)
    return GateResult("G2", not msgs, tuple(msgs))


# ------------------------------------------------------------------ G3
def g3_positioning_legal(content: ResumeContent, profile: Profile) -> GateResult:
    msgs: list[str] = []
    exps = {e.id: e for e in profile.experience}
    for shown, ver in zip(content.experience, content.verification_block.experience, strict=False):
        real = exps.get(ver.experience_id)
        if real is None:
            continue
        employers = {real.employer_display_options.full}
        if profile.disclosure_rules.allow_employer_anonymization and (
            real.employer_display_options.anonymized
        ):
            employers.add(real.employer_display_options.anonymized)
        if shown.employer_display not in employers:
            msgs.append(f"{ver.experience_id}: employer display {shown.employer_display!r} not allowed")
        titles = {real.title_display_options.exact}
        if real.title_display_options.handson_descriptor:
            titles.add(real.title_display_options.handson_descriptor)
        if shown.title_display not in titles:
            msgs.append(f"{ver.experience_id}: title display {shown.title_display!r} not allowed")
        if (ver.employer_real, ver.title_real) != (real.employer_real, real.title_real):
            msgs.append(f"{ver.experience_id}: verification block differs from profile")
    return GateResult("G3", not msgs, tuple(msgs))


# ------------------------------------------------------------------ G4
def g4_coverage(content: ResumeContent, jd: JDParsed, profile: Profile) -> GateResult:
    skills = [s.name for s in profile.skills if s.level != "familiar"]
    bullets = [b.text for e in content.experience for b in e.bullets]
    shown = " ".join([*content.skills_core, *bullets, *content.summary])
    supportable: list[str] = []
    present: list[str] = []
    for item in jd.must_have:
        names = [n for n in skills if _matches(n, [item])]
        if not names:
            continue
        supportable.append(item)
        if any(_matches(n, [shown]) for n in names):
            present.append(item)
    ratio = 1.0 if not supportable else len(present) / len(supportable)
    msgs = [f"coverage {ratio:.0%} ({len(present)}/{len(supportable)})"]
    msgs += [f"missing supportable requirement: {m}" for m in supportable if m not in present]
    return GateResult("G4", ratio >= COVERAGE_THRESHOLD, tuple(msgs))


# ------------------------------------------------------------------ G5
def g5_format(content: ResumeContent, pdf_path: Path | None = None) -> GateResult:
    msgs: list[str] = []
    text = resume_to_text(content)
    if pdf_path is not None:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        pages = len(reader.pages)
        if not 1 <= pages <= 2:
            msgs.append(f"{pages} pages; must be 1-2")
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        if not text.strip():
            msgs.append("PDF text layer is empty")
    upper = text.upper()
    positions = [upper.find(h) for h in _HEADINGS]
    if -1 in positions or positions != sorted(positions):
        msgs.append("section headings Experience/Education/Skills missing or out of order")
    bad = sum(1 for ch in text if ch == "�" or (ord(ch) < 32 and ch not in "\n\t\r"))
    if bad:
        msgs.append(f"{bad} garbage characters in text")
    words = len(text.split())
    if not MIN_RESUME_WORDS <= words <= MAX_RESUME_WORDS:
        msgs.append(f"{words} words; must be {MIN_RESUME_WORDS}-{MAX_RESUME_WORDS}")
    return GateResult("G5", not msgs, tuple(msgs))


# ------------------------------------------------------------------ G6
def g6_cover(letter: CoverLetter, archetype: Archetype, company: str | None = None) -> GateResult:
    from jobharness.compose.cover import MAX_WORDS, MIN_WORDS

    msgs: list[str] = []
    if not MIN_WORDS <= letter.word_count <= MAX_WORDS:
        msgs.append(f"{letter.word_count} words; must be {MIN_WORDS}-{MAX_WORDS}")
    if not any(s.role == "format" and "independent contractor" in s.text for s in letter.sentences):
        msgs.append("engagement-format sentence missing")
    low = letter.text.lower()
    msgs += [f"banned phrase: {p}" for p in banned_phrases(archetype) if p in low]
    if _PLACEHOLDER.search(letter.text):
        msgs.append("placeholder text present")
    if company and company.lower() not in low:
        msgs.append(f"company name {company!r} not mentioned")
    return GateResult("G6", not msgs, tuple(msgs))


# ------------------------------------------------------------------ G7
def g7_policy(
    content: ResumeContent,
    letter: CoverLetter | None,
    profile: Profile,
    positioning: Positioning,
    include_rate: bool = True,
) -> GateResult:
    msgs: list[str] = []
    text = (resume_to_text(content) + "\n" + (letter.text if letter else "")).lower()
    for phrase in profile.disclosure_rules.never_claim:
        if phrase.lower() in text:
            msgs.append(f"never_claim phrase present: {phrase!r}")
    if letter is not None:
        expected = engagement_sentence(positioning, include_rate)
        fmt = [s.text for s in letter.sentences if s.role == "format"]
        if fmt and fmt[0] != expected:
            msgs.append("engagement sentence differs from configured hours/rate")
    return GateResult("G7", not msgs, tuple(msgs))


def run_gates(
    content: ResumeContent,
    letter: CoverLetter | None,
    profile: Profile,
    positioning: Positioning,
    archetype: Archetype,
    jd: JDParsed,
    *,
    company: str | None = None,
    pdf_path: Path | None = None,
    previous: list[ResumeContent] | None = None,
    llm_labels: list[ClaimLabel] | None = None,
    include_rate: bool = True,
) -> list[GateResult]:
    results = [
        g1_truth(content, letter, profile, jd, company, llm_labels),
        g2_consistency(content, profile, previous),
        g3_positioning_legal(content, profile),
        g4_coverage(content, jd, profile),
        g5_format(content, pdf_path),
    ]
    if letter is not None:
        results.append(g6_cover(letter, archetype, company))
    results.append(g7_policy(content, letter, profile, positioning, include_rate))
    return results


__all__ = [
    "COVERAGE_THRESHOLD",
    "GateResult",
    "g1_truth",
    "g2_consistency",
    "g3_positioning_legal",
    "g4_coverage",
    "g5_format",
    "g6_cover",
    "g7_policy",
    "llm_verify_claims",
    "run_gates",
]
