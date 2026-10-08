"""Resume composition (spec §11.4 steps 5-7).

The LLM only rewrites the bullets of facts chosen by retrieval; everything
else (header, headline, summary, skills, dates, display names) is assembled
deterministically from the profile. Every LLM bullet is checked in code
(cited ids exist and belong to its role; no new numbers or entities). A role
that cannot be validated falls back to its original bullets verbatim, so the
output is always truthful.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from jobharness.compose.retrieval import (
    RetrievalResult,
    SelectedProject,
    SelectedRole,
    retrieve_facts,
)
from jobharness.eval.claims_check import FactInfo, check_claim, fact_index
from jobharness.llm.prompt_versions import default_version
from jobharness.llm.prompts import load_system_prompt
from jobharness.llm.provider import LLMProvider
from jobharness.schemas.archetype import Archetype
from jobharness.schemas.documents import (
    PositioningApplied,
    ResumeBullet,
    ResumeCertification,
    ResumeContent,
    ResumeDraft,
    ResumeEducation,
    ResumeExperience,
    ResumeHeader,
    ResumeLanguage,
    ResumeProject,
    RoleDraft,
    VerificationBlock,
    VerificationEntry,
)
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import Positioning
from jobharness.schemas.profile import Experience, Profile

MAX_BULLET_WORDS = 40


@dataclass
class ResumeResult:
    content: ResumeContent
    retrieval: RetrievalResult
    fallback_ids: list[str] = field(default_factory=list)
    llm_error: str | None = None
    iterations: int = 0


def _job_block(jd: JDParsed) -> str:
    return (
        "<UNTRUSTED_JOB>\n"
        + json.dumps(
            {
                "title": jd.title,
                "must_have": jd.must_have,
                "tech_stack": jd.tech_stack,
                "responsibilities": jd.responsibilities,
            },
            ensure_ascii=False,
        )
        + "\n</UNTRUSTED_JOB>"
    )


def _facts_block(sel: RetrievalResult) -> str:
    roles = [
        {
            "role_id": r.experience.id,
            "title": r.experience.title_real,
            "bullets": [{"id": b.bullet.id, "text": b.bullet.text} for b in r.bullets],
        }
        for r in sel.roles
        if r.bullets
    ]
    projects = [
        {
            "role_id": p.project.id,
            "title": p.project.name,
            "bullets": [{"id": b.bullet.id, "text": b.bullet.text} for b in p.bullets],
        }
        for p in sel.projects
    ]
    return "FACTS:\n" + json.dumps({"roles": roles, "projects": projects}, ensure_ascii=False)


def _validate(
    draft: RoleDraft, allowed: dict[str, str], index: dict[str, FactInfo]
) -> tuple[list[ResumeBullet], list[str]]:
    errors: list[str] = []
    out: list[ResumeBullet] = []
    if not draft.bullets:
        return [], [f"{draft.role_id}: no bullets"]
    if len(draft.bullets) > len(allowed):
        errors.append(f"{draft.role_id}: more bullets than facts ({len(allowed)})")
    for b in draft.bullets:
        if not b.source_fact_ids or any(i not in allowed for i in b.source_fact_ids):
            errors.append(f"{draft.role_id}: bullet cites ids outside this role: {b.source_fact_ids}")
            continue
        if len(b.text.split()) > MAX_BULLET_WORDS:
            errors.append(f"{draft.role_id}: bullet longer than {MAX_BULLET_WORDS} words")
            continue
        issues = check_claim(b.text, b.source_fact_ids, index)
        if issues:
            errors.append(
                f"{draft.role_id}: unsupported content {[str(i) for i in issues]} in {b.text!r}"
            )
            continue
        out.append(ResumeBullet(text=b.text, source_fact_ids=list(b.source_fact_ids)))
    return (out, errors) if not errors else ([], errors)


def display_names(exp: Experience, positioning: Positioning, profile: Profile) -> tuple[str, str, bool, bool]:
    """(employer, title, used_anonymized, used_descriptor)."""
    employer, anon = exp.employer_display_options.full, False
    if (
        positioning.employer_display == "anonymized"
        and profile.disclosure_rules.allow_employer_anonymization
        and exp.employer_display_options.anonymized
    ):
        employer, anon = exp.employer_display_options.anonymized, True
    title, desc = exp.title_display_options.exact, False
    if positioning.title_display == "handson_descriptor" and exp.title_display_options.handson_descriptor:
        title, desc = exp.title_display_options.handson_descriptor, True
    return employer, title, anon, desc


async def compose_resume(
    profile: Profile,
    archetype: Archetype,
    positioning: Positioning,
    jd: JDParsed,
    provider: LLMProvider,
    *,
    model: str,
    today: date,
    temperature: float = 0.4,
    max_iterations: int = 2,
    feedback: str = "",
) -> ResumeResult:
    sel = retrieve_facts(profile, archetype, positioning, jd, today=today)
    index = fact_index(profile)
    allowed: dict[str, dict[str, str]] = {}
    for r in sel.roles:
        if r.bullets:
            allowed[r.experience.id] = {b.bullet.id: b.bullet.text for b in r.bullets}
    for p in sel.projects:
        allowed[p.project.id] = {b.bullet.id: b.bullet.text for b in p.bullets}

    chosen: dict[str, list[ResumeBullet]] = {}
    llm_error: str | None = None
    iterations = 0
    base_user = _facts_block(sel) + "\n\n" + _job_block(jd)
    if feedback:
        base_user += "\n\nReviewer feedback on an earlier version; address it:\n- " + feedback
    user = base_user
    system = load_system_prompt("resume_compose", default_version("resume_compose"))
    if allowed:
        for attempt in range(1, max_iterations + 2):
            iterations = attempt
            try:
                out, _meta = await provider.generate_structured(
                    purpose="resume_compose",
                    model=model,
                    system=system,
                    user=user,
                    schema=ResumeDraft,
                    temperature=temperature,
                    max_tokens=2048,
                    prompt_version=default_version("resume_compose"),
                )
            except Exception as err:  # provider failure -> verbatim fallback
                llm_error = str(err)[:200]
                break
            assert isinstance(out, ResumeDraft)
            errors: list[str] = []
            seen: set[str] = set()
            for rd in [*out.roles, *out.projects]:
                if rd.role_id not in allowed or rd.role_id in chosen:
                    continue
                seen.add(rd.role_id)
                ok, errs = _validate(rd, allowed[rd.role_id], index)
                if errs:
                    errors.extend(errs)
                else:
                    chosen[rd.role_id] = ok
            errors.extend(f"{rid}: missing from output" for rid in allowed if rid not in chosen and rid not in seen)
            if len(chosen) == len(allowed):
                break
            user = base_user + "\n\nYour previous answer had problems; fix them:\n- " + "\n- ".join(errors)

    fallback: list[str] = []

    def bullets_for(rid: str, selected: SelectedRole | SelectedProject) -> list[ResumeBullet]:
        if rid in chosen:
            return chosen[rid]
        fallback.append(rid)
        return [
            ResumeBullet(text=b.bullet.text, source_fact_ids=[b.bullet.id]) for b in selected.bullets
        ]

    experience: list[ResumeExperience] = []
    verification: list[VerificationEntry] = []
    all_anon = all_desc = True
    for r in sel.roles:
        e = r.experience
        employer, title, anon, desc = display_names(e, positioning, profile)
        all_anon &= anon
        all_desc &= desc
        experience.append(
            ResumeExperience(
                employer_display=employer,
                title_display=title,
                start=e.start,
                end=e.end,
                bullets=bullets_for(e.id, r) if r.bullets else [],
            )
        )
        verification.append(
            VerificationEntry(
                experience_id=e.id,
                employer_real=e.employer_real,
                title_real=e.title_real,
                start=e.start,
                end=e.end,
            )
        )
    projects = [
        ResumeProject(name=p.project.name, url=p.project.url, bullets=bullets_for(p.project.id, p))
        for p in sel.projects
    ]
    earlier = None
    if sel.earlier_roles:
        parts = []
        for e in sel.earlier_roles:
            employer, title, _a, _d = display_names(e, positioning, profile)
            parts.append(f"{title}, {employer} ({e.start[:4]}–{(e.end or 'present')[:4]})")
        earlier = "Earlier experience: " + "; ".join(parts) + "."

    ident = profile.identity
    links = {k: v for k, v in ident.links.model_dump().items() if v}
    content = ResumeContent(
        header=ResumeHeader(
            full_name=ident.public_alias or ident.full_name,
            email=ident.email,
            phone=ident.phone,
            location=f"{ident.location.city}, {ident.location.country}",
            links=links,
        ),
        headline=archetype.headline_templates[0],
        summary=[s.text for s in sel.summary_facts],
        skills_core=[s.name for s in sel.skills],
        experience=experience,
        earlier_experience_line=earlier,
        education=[
            ResumeEducation(
                institution=ed.institution, degree=ed.degree, field=ed.field,
                start=ed.start, end=ed.end, source_fact_id=ed.id,
            )
            for ed in profile.education
        ],
        certifications=[
            ResumeCertification(name=c.name, issuer=c.issuer, date=c.date, source_fact_id=c.id)
            for c in profile.certifications
        ],
        projects=projects,
        languages=[ResumeLanguage(lang=x.lang, level=x.level) for x in ident.languages],
        positioning_applied=PositioningApplied(
            employer_display="anonymized" if experience and all_anon else "full",
            title_display="handson_descriptor" if experience and all_desc else "exact",
            leadership_visibility=positioning.leadership_visibility,
            recency_window_years=positioning.recency_window_years,
        ),
        verification_block=VerificationBlock(experience=verification),
    )
    return ResumeResult(
        content=content, retrieval=sel, fallback_ids=fallback, llm_error=llm_error,
        iterations=iterations,
    )


__all__ = ["ResumeResult", "compose_resume", "display_names"]
