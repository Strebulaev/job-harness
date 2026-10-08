"""Weighted scoring + archetype selection (spec §11.3).

Components (0-100): stack match 30, rate fit 20, TZ/overlap 15,
engagement fit 10, scope/hours fit 10, company/posting quality 10.
An overqualification penalty (up to -15, applied when the posting's comp
band sits above the Principal's ceiling) is subtracted from the total.
All weights are spec constants; they live here so a future config move is
a one-line change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jobharness.parse.normalizers import NormalizedCompensation
from jobharness.schemas.archetype import Archetype
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import Positioning
from jobharness.schemas.profile import Profile

#: spec §11.3 component weights (max per component).
WEIGHTS: dict[str, float] = {
    "stack_match": 30.0,
    "rate_fit": 20.0,
    "tz_overlap": 15.0,
    "engagement_fit": 10.0,
    "scope_hours_fit": 10.0,
    "quality": 10.0,
}
OVERQUALIFICATION_PENALTY_MAX: float = 15.0

_SKILL_LEVEL_SCORE: dict[str, float] = {
    "familiar": 0.4,
    "working": 0.7,
    "proficient": 0.9,
    "expert": 1.0,
}


@dataclass(slots=True)
class ScoreBreakdown:
    components: dict[str, float] = field(default_factory=dict)
    overqualification_penalty: float = 0.0
    flags: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        base = sum(self.components.values())
        return max(0.0, min(100.0, base - self.overqualification_penalty))

    def as_dict(self) -> dict[str, float]:
        out: dict[str, float] = dict(self.components)
        out["overqualification_penalty"] = self.overqualification_penalty
        out["total"] = self.total
        return out


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _term_overlap(a: str, b: str) -> float:
    """Fraction of tokens in ``a`` present in ``b`` (0..1)."""
    ta = set(_norm(a).split())
    if not ta:
        return 0.0
    tb = set(_norm(b).split())
    return len(ta & tb) / len(ta)


def stack_match_score(
    parsed: JDParsed, profile: Profile, max_score: float = WEIGHTS["stack_match"]
) -> tuple[float, list[str]]:
    """Component 1: weighted overlap between JD must_have/tech_stack and
    profile skills (level weighted)."""
    skill_names: dict[str, float] = {
        _norm(s.name): _SKILL_LEVEL_SCORE[s.level] for s in profile.skills
    }
    bullets: list[str] = [
        _norm(b.text) + " " + " ".join(_norm(t) for t in b.tags)
        for e in profile.experience
        for b in e.bullets
    ] + [_norm(p.summary or "") for p in profile.projects]

    must = [m for m in parsed.must_have if _norm(m)]
    stack = [t for t in parsed.tech_stack if _norm(t)]
    if not must and not stack:
        return 0.5 * max_score, ["stack_match: no must_have/tech_stack to match"]

    # Must-have terms must be covered; stack terms are a bonus.
    must_hits: list[float] = []
    for term in must:
        n = _norm(term)
        if n in skill_names:
            must_hits.append(skill_names[n])
        else:
            hit = 0.0
            for name, score in skill_names.items():
                if n in name or name in n:
                    hit = max(hit, score * 0.8)
            for b in bullets:
                if n in b:
                    hit = max(hit, 0.5)
            must_hits.append(hit)

    stack_hits: list[float] = []
    for term in stack:
        n = _norm(term)
        if n in skill_names:
            stack_hits.append(skill_names[n])
        else:
            hit = 0.0
            for name, score in skill_names.items():
                if n in name or name in n:
                    hit = max(hit, score * 0.8)
            for b in bullets:
                if n in b:
                    hit = max(hit, 0.5)
            stack_hits.append(hit)

    must_frac = sum(must_hits) / len(must_hits) if must_hits else 0.0
    stack_frac = sum(stack_hits) / len(stack_hits) if stack_hits else 0.0
    score = max_score * (0.7 * must_frac + 0.3 * stack_frac)
    return min(max_score, score), [
        f"stack_match: {len(must_hits)} must + {len(stack_hits)} stack"
    ]


def rate_fit_score(
    normalized: NormalizedCompensation | None, positioning: Positioning
) -> tuple[float, list[str]]:
    """Component 2 (max 20): position of the posting band vs
    ``positioning.rate_expectation_usd_month``."""
    lo = positioning.rate_expectation_usd_month.min
    hi = positioning.rate_expectation_usd_month.max
    if normalized is None:
        return 10.0, ["rate_fit: unknown compensation -> neutral"]
    p_lo, p_hi = normalized.usd_min_month, normalized.usd_max_month
    if p_hi < lo:
        return 0.0, [f"rate_fit: band ${p_lo:.0f}-${p_hi:.0f} below expectation"]
    if p_lo > hi:
        return 5.0, [f"rate_fit: band ${p_lo:.0f}-${p_hi:.0f} above expectation"]
    # Band overlaps expectation. Score is best when the expectation window
    # sits inside the band; degrades toward the edges.
    ideal_overlap = min(hi, p_hi) - max(lo, p_lo)
    frac = max(0.0, ideal_overlap) / max(hi - lo, 1.0)
    score = 10.0 + 10.0 * frac
    return min(20.0, score), [f"rate_fit: band ${p_lo:.0f}-${p_hi:.0f}"]


def tz_overlap_score(
    overlap: float | None, min_hours: float, target_hours: float
) -> tuple[float, list[str]]:
    """Component 3 (max 15): overlap between Principal and posting windows."""
    if overlap is None:
        return 7.5, ["tz_overlap: unknown -> neutral"]
    if overlap <= 0:
        return 0.0, ["tz_overlap: no overlap"]
    if overlap >= target_hours:
        return 15.0, [f"tz_overlap: {overlap:.1f}h >= target {target_hours:.1f}h"]
    if overlap >= min_hours:
        frac = (overlap - min_hours) / max(target_hours - min_hours, 1e-9)
        return 10.0 + 5.0 * frac, [f"tz_overlap: {overlap:.1f}h between min and target"]
    return 0.0, [f"tz_overlap: {overlap:.1f}h below min"]


def engagement_fit_score(parsed: JDParsed) -> tuple[float, list[str]]:
    """Component 4 (max 10): explicit contractor/B2B beats unknown."""
    et = parsed.engagement_type
    if et in ("contractor", "b2b", "freelance", "project"):
        return 10.0, [f"engagement_fit: {et}"]
    if et == "unknown":
        return 5.0, ["engagement_fit: unknown -> neutral"]
    return 2.0, [f"engagement_fit: {et} (not contractor-friendly)"]


def scope_hours_fit(
    parsed: JDParsed, positioning: Positioning
) -> tuple[float, list[str]]:
    """Component 5 (max 10): does the posting's hours/week fit the
    Principal's working range?"""
    if parsed.hours_per_week is None:
        return 5.0, ["scope_hours_fit: hours unknown -> neutral"]
    p_lo, p_hi = parsed.hours_per_week
    exp_lo = positioning.hours_week.min
    exp_hi = positioning.hours_week.max
    if p_hi <= exp_hi and p_lo <= exp_hi:
        # Posting range is mostly inside the expectation.
        ideal = min(p_hi, exp_hi) - max(p_lo, exp_lo)
        span = max(p_hi - p_lo, 1.0)
        return 10.0 * max(0.0, min(1.0, ideal / span + 0.5)), [
            f"scope_hours_fit: {p_lo}-{p_hi} h/wk"
        ]
    if p_lo > exp_hi:
        return 3.0, [f"scope_hours_fit: {p_lo}-{p_hi} h/wk above expectation"]
    return 5.0, [f"scope_hours_fit: {p_lo}-{p_hi} h/wk"]


def quality_score(parsed: JDParsed) -> tuple[float, list[str]]:
    """Component 6 (max 10): clear JD, named hiring contact, known company —
    from JD text only (spec §11.3: no external scraping)."""
    score = 0.0
    notes: list[str] = []
    if parsed.company:
        score += 4.0
        notes.append(f"company: {parsed.company}")
    if parsed.application_email:
        score += 3.0
        notes.append("named application email")
    text_len = sum(len(r) for r in parsed.responsibilities) + len(parsed.must_have) * 8
    if len(parsed.must_have) >= 3:
        score += 2.0
        notes.append(f"clear JD ({len(parsed.must_have)} requirements)")
    elif text_len > 0:
        score += 1.0
        notes.append("partial JD detail")
    if parsed.application_method == "email":
        score += 1.0
        notes.append("email application channel")
    return min(10.0, score), notes


def overqualification_penalty(
    normalized: NormalizedCompensation | None, positioning: Positioning
) -> float:
    """Up to -15 when the posting's rate band sits above the Principal's
    ceiling (spec §11.3: 'when expected rate cannot be met')."""
    if normalized is None:
        return 0.0
    ceiling = positioning.rate_expectation_usd_month.max
    band_hi = normalized.usd_max_month
    if band_hi <= ceiling:
        return 0.0
    # Penalty scales with how far above the ceiling the band starts.
    ratio = band_hi / ceiling
    return OVERQUALIFICATION_PENALTY_MAX * min(1.0, max(0.0, (ratio - 1.0) * 2.0))


def score_job(
    parsed: JDParsed,
    profile: Profile,
    positioning: Positioning,
    normalized: NormalizedCompensation | None,
    overlap: float | None,
    min_overlap_hours: float,
    target_overlap_hours: float,
) -> ScoreBreakdown:
    """Run all six components + the overqualification penalty."""
    bd = ScoreBreakdown()
    s, _ = stack_match_score(parsed, profile)
    bd.components["stack_match"] = round(s, 2)
    s, _ = rate_fit_score(normalized, positioning)
    bd.components["rate_fit"] = round(s, 2)
    s, _ = tz_overlap_score(overlap, min_overlap_hours, target_overlap_hours)
    bd.components["tz_overlap"] = round(s, 2)
    s, _ = engagement_fit_score(parsed)
    bd.components["engagement_fit"] = round(s, 2)
    s, _ = scope_hours_fit(parsed, positioning)
    bd.components["scope_hours_fit"] = round(s, 2)
    s, _ = quality_score(parsed)
    bd.components["quality"] = round(s, 2)
    bd.overqualification_penalty = round(
        overqualification_penalty(normalized, positioning), 2
    )
    return bd


# ---------------------------------------------------------------- archetypes
def _archetype_text(parsed: JDParsed) -> str:
    """Raw text used for jd_match_signals / nice_to_have keyword matches."""
    parts: list[str] = [
        parsed.title or "",
        *parsed.tech_stack,
        *parsed.responsibilities,
    ]
    if parsed.company:
        parts.append(parsed.company)
    return _norm(" ".join(p for p in parts if p))


def select_archetypes(
    parsed: JDParsed, archetypes: dict[str, Archetype]
) -> list[tuple[str, float]]:
    """Score every archetype by jd_match_signals + keyword overlap.

    The archetype's ``must_have_keywords`` describe the job it owns, so they
    are matched against the JD's *required* terms first (heaviest weight);
    ``jd_match_signals`` and ``nice_to_have_keywords`` then match the raw
    JD text. Returns ``(archetype_id, score)`` sorted descending; the router
    keeps the top-2 and a top score below the threshold means
    ``no_archetype``.
    """
    text = _archetype_text(parsed)
    required = {_norm(t) for t in parsed.must_have}
    scored: list[tuple[str, float]] = []
    for arch in archetypes.values():
        must = [k for k in arch.must_have_keywords if _norm(k)]
        # Match must_have keywords: exact match in required set, OR whole-word
        # match in the archetype text (to avoid false positives like 'api'
        # matching 'fastapi' or 'sql' matching 'postgresql').
        must_hits = sum(
            1
            for k in must
            if _norm(k) in required
            or re.search(rf"\b{re.escape(_norm(k))}\b", text)
        )
        must_score = 8.0 * (must_hits / len(must)) if must else 0.0
        signals = [s.lower() for s in arch.jd_match_signals if s]
        sig_hits = sum(1 for s in signals if s in text)
        signal_score = 8.0 * (sig_hits / len(signals)) if signals else 0.0
        nice = [k for k in arch.nice_to_have_keywords if _norm(k)]
        nice_hits = sum(
            1
            for k in nice
            if _norm(k) in text or re.search(rf"\b{re.escape(_norm(k))}\b", text)
        )
        nice_score = 2.0 * (nice_hits / len(nice)) if nice else 0.0
        total = round(must_score + signal_score + nice_score, 2)
        scored.append((arch.id, total))
    scored.sort(key=lambda t: (-t[1], t[0]))
    return scored


__all__ = [
    "OVERQUALIFICATION_PENALTY_MAX",
    "WEIGHTS",
    "ScoreBreakdown",
    "engagement_fit_score",
    "overqualification_penalty",
    "quality_score",
    "rate_fit_score",
    "scope_hours_fit",
    "select_archetypes",
    "stack_match_score",
    "tz_overlap_score",
]
