"""Cover letter composition (spec §11.4).

Structure: observation about the job, one proof point from a cited fact, the
engagement-format sentence (built in code), optional overqualification
rationale, closing. The LLM writes observation, proof and closing; code builds
the rest and checks everything. On repeated failure a deterministic template
built from the selected facts is used, so a letter always exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from jobharness.compose.resume import display_names
from jobharness.compose.retrieval import RetrievalResult
from jobharness.eval.claims_check import check_claim, check_text, fact_index
from jobharness.llm.prompt_versions import default_version
from jobharness.llm.prompts import load_system_prompt
from jobharness.llm.provider import LLMProvider
from jobharness.schemas.archetype import Archetype
from jobharness.schemas.documents import CoverDraft, CoverLetter, CoverSentence
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import Positioning
from jobharness.schemas.profile import Profile

MIN_WORDS, MAX_WORDS = 120, 180
BANNED_GLOBAL: tuple[str, ...] = (
    "passionate", "rockstar", "ninja", "synergy", "go-getter", "team player",
    "hit the ground running", "results-driven", "dynamic", "guru", "self-starter",
)
STYLE_SENTENCES: tuple[str, ...] = (
    "I prefer clear scopes, short written weekly updates, and delivery in small, "
    "reviewable increments so you can see progress early.",
    "I am comfortable owning a problem end to end, from the first design sketch "
    "through to production support.",
    "I document decisions as I go, so the work stays easy to hand over or extend later.",
    "I raise risks and trade-offs early and in plain language, so you can decide with "
    "full information.",
    "I write tests alongside the code and keep changes small enough to review "
    "comfortably in one sitting.",
    "I am used to working asynchronously across time zones and keep a predictable "
    "overlap window for calls.",
    "I treat your budget as my own and flag early when a simpler approach would "
    "deliver the same result.",
)
RATIONALE = (
    "I am deliberately looking for a hands-on contractor engagement rather than a "
    "management role."
)


@dataclass
class CoverResult:
    letter: CoverLetter
    used_fallback: bool = False
    llm_error: str | None = None
    problems: list[str] = field(default_factory=list)


def banned_phrases(archetype: Archetype) -> list[str]:
    return [*BANNED_GLOBAL, *(p.lower() for p in archetype.cover_letter.avoid_phrases)]


def engagement_sentence(positioning: Positioning, include_rate: bool = True) -> str:
    h, r = positioning.hours_week, positioning.rate_expectation_usd_month
    label = positioning.engagement_label
    tag = label[label.index("("):] if "(" in label else f"({label})"
    s = f"I work as an independent contractor {tag}, typically {h.min:g}–{h.max:g} hours per week"
    if include_rate:
        s += f", with a rate expectation of ${r.min:,.0f}–${r.max:,.0f} per month"
    return s + "."


def _job_texts(jd: JDParsed, company: str | None) -> list[str]:
    return [jd.title, company or "", *jd.must_have, *jd.tech_stack, *jd.responsibilities]


def _job_block(jd: JDParsed, company: str | None) -> str:
    return "<UNTRUSTED_JOB>\n" + json.dumps(
        {
            "title": jd.title,
            "company": company,
            "must_have": jd.must_have,
            "tech_stack": jd.tech_stack,
            "responsibilities": jd.responsibilities,
        },
        ensure_ascii=False,
    ) + "\n</UNTRUSTED_JOB>"


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _assemble(
    parts: list[CoverSentence], positioning: Positioning, include_rate: bool,
    overqualified: bool,
) -> list[CoverSentence]:
    obs, *rest = parts
    out = [obs, *rest[:-1]]
    out.append(CoverSentence(text=engagement_sentence(positioning, include_rate), role="format"))
    if overqualified:
        out.append(CoverSentence(text=RATIONALE, role="rationale"))
    out.append(rest[-1])
    return out


def _pad(sentences: list[CoverSentence]) -> list[CoverSentence]:
    """Insert style sentences (before the closing) until the minimum length."""
    out = list(sentences)
    for style in STYLE_SENTENCES:
        if CoverLetter(sentences=out).word_count >= MIN_WORDS:
            break
        out.insert(len(out) - 1, CoverSentence(text=style, role="style"))
    return out


async def compose_cover(
    profile: Profile,
    archetype: Archetype,
    positioning: Positioning,
    jd: JDParsed,
    retrieval: RetrievalResult,
    provider: LLMProvider,
    *,
    model: str,
    company: str | None = None,
    include_rate: bool = True,
    overqualified: bool = False,
    temperature: float = 0.4,
    max_iterations: int = 2,
    feedback: str = "",
) -> CoverResult:
    index = fact_index(profile)
    candidates: dict[str, str] = {}
    for r in retrieval.roles:
        for b in r.bullets:
            candidates[b.bullet.id] = b.bullet.text
    job_texts = _job_texts(jd, company)
    banned = banned_phrases(archetype)
    system = load_system_prompt("cover_compose", default_version("cover_compose"))
    base_user = (
        "FACTS:\n"
        + json.dumps([{"id": i, "text": t} for i, t in candidates.items()], ensure_ascii=False)
        + "\n\n"
        + _job_block(jd, company)
        + (f"\n\nReviewer feedback on an earlier version; address it:\n- {feedback}" if feedback else "")
    )
    user = base_user
    problems: list[str] = []
    llm_error: str | None = None

    if candidates:
        for _ in range(max_iterations + 1):
            try:
                out, _meta = await provider.generate_structured(
                    purpose="cover_compose", model=model, system=system, user=user,
                    schema=CoverDraft, temperature=temperature, max_tokens=700,
                    prompt_version=default_version("cover_compose"),
                )
            except Exception as e:
                llm_error = str(e)[:200]
                break
            assert isinstance(out, CoverDraft)
            problems = []
            if not out.proof_fact_ids or any(i not in candidates for i in out.proof_fact_ids):
                problems.append(f"proof_fact_ids must be from {sorted(candidates)}")
            else:
                issues = check_claim(
                    out.proof, out.proof_fact_ids, index, entity_support=job_texts
                )
                problems += [f"proof has unsupported {i}" for i in issues]
            problems += [
                f"observation has unsupported {i}"
                for i in check_text(out.observation, job_texts)
            ]
            problems += [f"closing has unsupported {i}" for i in check_text(out.closing, [])]
            parts = [
                CoverSentence(text=out.observation.strip(), role="observation"),
                CoverSentence(
                    text=out.proof.strip(), role="proof", source_fact_ids=list(out.proof_fact_ids)
                ),
                CoverSentence(text=out.closing.strip(), role="cta"),
            ]
            letter = CoverLetter(
                sentences=_pad(_assemble(parts, positioning, include_rate, overqualified))
            )
            low = letter.text.lower()
            problems += [f"banned phrase: {p}" for p in banned if p in low]
            if company and company.lower() not in low:
                problems.append(f"mention the company name {company!r} in the observation")
            if letter.word_count < MIN_WORDS:
                problems.append(
                    f"letter is {letter.word_count} words; must be at least {MIN_WORDS}: "
                    "make observation and proof a little longer"
                )
            if letter.word_count > MAX_WORDS:
                problems.append(
                    f"letter is {letter.word_count} words; must be at most {MAX_WORDS} "
                    "(a fixed engagement sentence is added by the system)"
                )
            if not problems:
                return CoverResult(letter=letter)
            user = base_user + "\n\nFix these problems:\n- " + "\n- ".join(problems)

    return CoverResult(
        letter=_fallback(
            retrieval, jd, company, positioning, include_rate, overqualified, profile
        ),
        used_fallback=True,
        llm_error=llm_error,
        problems=problems,
    )


def _fallback(
    retrieval: RetrievalResult,
    jd: JDParsed,
    company: str | None,
    positioning: Positioning,
    include_rate: bool,
    overqualified: bool,
    profile: Profile,
) -> CoverLetter:
    focus = (jd.responsibilities or jd.must_have or [jd.title])[0].rstrip(".")
    where = f" at {company}" if company else ""
    obs = CoverSentence(
        text=(
            f"Your posting for {jd.title}{where} centres on {focus}, which is close to the "
            "work I do every day."
        ),
        role="observation",
    )
    proof: list[CoverSentence] = []
    for r in retrieval.roles:
        if r.bullets:
            b = r.bullets[0].bullet
            exp = r.experience
            employer, title, _a, _d = display_names(exp, positioning, profile)
            proof.append(
                CoverSentence(
                    text=f"As {title} at {employer}, I {_lower_first(b.text)}",
                    role="proof",
                    source_fact_ids=[exp.id, b.id],
                )
            )
            break
    if retrieval.skills:
        names = [s.name for s in retrieval.skills[:3]]
        stack = ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]
        proof.append(
            CoverSentence(
                text=f"My core stack includes {stack}.",
                role="proof",
                source_fact_ids=[s.id for s in retrieval.skills[:3]],
            )
        )
    cta = CoverSentence(
        text="I would welcome a short call to discuss whether I can help, and I am happy to "
        "start with a small paid task.",
        role="cta",
    )
    out = [obs, *proof]
    out.append(CoverSentence(text=engagement_sentence(positioning, include_rate), role="format"))
    if overqualified:
        out.append(CoverSentence(text=RATIONALE, role="rationale"))
    out.append(cta)
    return CoverLetter(sentences=_pad(out))


__all__ = [
    "BANNED_GLOBAL",
    "CoverResult",
    "banned_phrases",
    "compose_cover",
    "engagement_sentence",
]
