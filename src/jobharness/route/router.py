"""Router orchestrator (spec §11.3): filters -> score -> archetype ->
shortlist. Pure function over a parsed JD + normalized compensation; the
CLI layer persists the result through the state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from jobharness.parse.normalizers import NormalizedCompensation
from jobharness.route import filters, scoring
from jobharness.route.overqualification import Overqualification, evaluate
from jobharness.schemas.archetype import Archetype
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import Positioning
from jobharness.schemas.profile import Profile
from jobharness.settings import Settings

#: Top archetype score below this means ``no_archetype`` (spec §11.3).
ARCHETYPE_MIN_SCORE: float = 4.5


@dataclass(slots=True)
class RouteResult:
    """Everything the router decided for one job."""

    rejected: bool
    reject_reasons: list[str]
    flags: list[str] = field(default_factory=list)
    score: float | None = None
    breakdown: dict[str, float] | None = None
    archetype: str | None = None
    archetype_top2: list[tuple[str, float]] = field(default_factory=list)
    overqualification: Overqualification | None = None
    overlap_hours: float | None = None
    notes: list[str] = field(default_factory=list)
    filter_details: list[dict[str, str]] = field(default_factory=list)

    @property
    def shortlisted(self) -> bool:
        return not self.rejected and self.score is not None

    def as_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "rejected": self.rejected,
            "reject_reasons": self.reject_reasons,
            "flags": self.flags,
            "score": self.score,
            "breakdown": self.breakdown,
            "archetype": self.archetype,
            "archetype_top2": self.archetype_top2,
            "overlap_hours": self.overlap_hours,
            "filter_details": self.filter_details,
            "notes": self.notes,
        }
        if self.overqualification is not None:
            out["positioning_applied"] = self.overqualification.positioning_applied()
        return out


def route_job(
    parsed: JDParsed,
    profile: Profile,
    positioning: Positioning,
    archetypes: dict[str, Archetype],
    settings: Settings,
    normalized_comp: NormalizedCompensation | None = None,
    reference: datetime | None = None,
) -> RouteResult:
    """Run the full router pipeline for one parsed job."""
    principal_tz = settings.principal.timezone
    principal_window = (
        settings.principal.work_window_local.start,
        settings.principal.work_window_local.end,
    )
    router_cfg = settings.router

# --- hard filters
    filter_results = filters.run_hard_filters(
        parsed,
        normalized_comp,
        router_cfg,
        principal_tz,
        principal_window,
        settings.principal.min_overlap_hours,
        reference,
    )
    reject_reasons: list[str] = []
    flag_set: list[str] = []
    details: list[dict[str, str]] = []
    for name, res in filter_results:
        details.append(
            {
                "filter": name,
                "outcome": "reject" if res.reason else ("flag" if res.flag else "pass"),
                "value": res.reason or res.flag or "",
                "detail": res.detail,
            }
        )
        if res.reason:
            reject_reasons.append(res.reason)
        elif res.flag:
            flag_set.append(res.flag)

    overlap: float | None = None
    pw = filters.posting_window(parsed)
    if pw is not None and parsed.required_overlap:
        ro = parsed.required_overlap
        tz = str(ro["tz"])
        overlap = filters.overlap_hours(
            principal_tz, principal_window, tz, pw, reference
        )

    # --- overqualification (independent of filters)
    oq = evaluate(positioning, parsed.seniority)
    if oq.handson_focus:
        flag_set.append("overqualification_handson_focus")

    # Always compute score for explain output, even if rejected.
    bd = scoring.score_job(
        parsed,
        profile,
        positioning,
        normalized_comp,
        overlap,
        settings.principal.min_overlap_hours,
        settings.principal.target_overlap_hours,
    )
    score = bd.total

    if reject_reasons:
        return RouteResult(
            rejected=True,
            reject_reasons=reject_reasons,
            flags=flag_set,
            score=bd.total,
            breakdown=bd.as_dict(),
            archetype=None,
            archetype_top2=[],
            overqualification=oq,
            overlap_hours=overlap,
            filter_details=details,
            notes=[d["detail"] for d in details if d["detail"]],
        )

    # --- scoring
    bd = scoring.score_job(
        parsed,
        profile,
        positioning,
        normalized_comp,
        overlap,
        settings.principal.min_overlap_hours,
        settings.principal.target_overlap_hours,
    )
    score = bd.total

    # --- archetype selection (top-2 stored; top below threshold -> reject)
    top2 = scoring.select_archetypes(parsed, archetypes)
    if top2[0][1] < ARCHETYPE_MIN_SCORE:
        return RouteResult(
            rejected=True,
            reject_reasons=["no_archetype"],
            flags=flag_set,
            score=score,
            breakdown=bd.as_dict(),
            archetype=None,
            archetype_top2=top2[:2],
            overqualification=oq,
            overlap_hours=overlap,
            filter_details=details,
            notes=["no archetype scored >= threshold"],
        )

    result = RouteResult(
        rejected=False,
        reject_reasons=[],
        flags=flag_set,
        score=score,
        breakdown=bd.as_dict(),
        archetype=top2[0][0],
        archetype_top2=top2[:2],
        overqualification=oq,
        overlap_hours=overlap,
        filter_details=details,
    )
    if score < router_cfg.min_score_to_apply:
        result.notes.append(
            f"score {score:.1f} < min_score_to_apply {router_cfg.min_score_to_apply}"
        )
    return result


__all__ = ["ARCHETYPE_MIN_SCORE", "RouteResult", "route_job"]
