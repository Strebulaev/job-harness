"""Hard filters for the router (spec §11.3, filters 1-8, in order).

A filter either rejects the job (its reason is recorded) or keeps it,
possibly adding a ``flag`` (e.g. ``verify_engagement``, ``ask_rate``). All
filters are pure: they read the parsed JD + normalized compensation and
return :class:`FilterResult`. The router applies them in the spec's order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from jobharness.parse.normalizers import NormalizedCompensation
from jobharness.schemas.jd import JDParsed
from jobharness.settings import RouterConfig

#: Default posting window when the JD gives no required_overlap
#: (spec §11.3 filter 5).
DEFAULT_POSTING_WINDOW: tuple[str, str] = ("09:00", "18:00")

#: Red-flag blocklist (spec §11.3 filter 8): canonical reason codes ->
#: patterns the parser labels its red_flags with.
RED_FLAG_PATTERNS: dict[str, tuple[str, ...]] = {
    "unpaid_trial": ("unpaid", "trial without pay", "no pay"),
    "equity_only": ("equity",),
    "pay_to_apply": (
        "pay to apply",
        "application fee",
        "pay to apply",
        "pay_to_apply",
        "assessment fee",
    ),
}


@dataclass(slots=True)
class FilterResult:
    """Outcome of one hard filter.

    ``reject`` -> the job is rejected with ``reason``.
    ``flag`` -> the job survives; the flag is recorded for scoring and
    explain output. ``None`` -> clean.
    """

    reason: str | None = None
    flag: str | None = None
    detail: str = ""


def _parse_time(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


def overlap_hours(
    tz_a: str,
    window_a: tuple[str, str],
    tz_b: str,
    window_b: tuple[str, str],
    reference: datetime | None = None,
) -> float:
    """Hours of overlap between two local windows in possibly different IANA
    timezones.

    Both windows are converted to UTC on the reference date (``reference``
    or today) and the intersection is taken. A window that crosses midnight
    (end < start, e.g. 22:00-06:00) is treated as next-day. The result is
    clipped to [0, 24].
    """
    zone_a = ZoneInfo(tz_a)
    zone_b = ZoneInfo(tz_b)
    ref = (reference or datetime.now()).date()

    def span(
        tz: ZoneInfo, window: tuple[str, str], local_date: date
    ) -> tuple[datetime, datetime]:
        start = datetime.combine(local_date, _parse_time(window[0]), tzinfo=tz)
        end = datetime.combine(local_date, _parse_time(window[1]), tzinfo=tz)
        if end <= start:
            end = end + timedelta(days=1)
        return start, end

    w1 = span(zone_a, window_a, ref)
    w2 = span(zone_b, window_b, ref)
    start = max(w1[0], w2[0])
    end = min(w1[1], w2[1])
    delta = (end - start).total_seconds() / 3600.0
    return max(0.0, min(24.0, delta))


def posting_window(parsed: JDParsed) -> tuple[str, str] | None:
    """The posting's required window, or None when unknown."""
    ro = parsed.required_overlap
    if (
        isinstance(ro, dict)
        and ro.get("tz")
        and ro.get("start")
        and ro.get("end")
    ):
        try:
            ZoneInfo(str(ro["tz"]))
        except Exception:
            return None
        return (str(ro["start"]), str(ro["end"]))
    return None


def run_hard_filters(
    parsed: JDParsed,
    normalized_comp: NormalizedCompensation | None,
    router: RouterConfig,
    principal_tz: str,
    principal_window: tuple[str, str],
    min_overlap_hours: float,
    reference: datetime | None = None,
) -> list[tuple[str, FilterResult]]:
    """Run all 8 hard filters in the spec's order.

    Returns ``(filter_name, result)`` pairs; ``result.reason`` is set when
    the job is rejected, ``result.flag`` when it survives with a flag.
    All filters are evaluated; rejection does not short-circuit so that
    all applicable reasons are collected (spec §11.3: "any failure -> rejected,
    reasons stored").
    """
    results: list[tuple[str, FilterResult]] = []

    # 1. engagement_type
    if parsed.engagement_type == "employee":
        results.append(
            (
                "engagement_type",
                FilterResult(
                    reason="engagement_type_employee",
                    detail=f"engagement_type={parsed.engagement_type}",
                ),
            )
        )
    elif parsed.engagement_type == "unknown":
        allowed = [e.lower() for e in router.engagement_types_allow]
        if allowed and parsed.engagement_type not in allowed:
            results.append(
                (
                    "engagement_type",
                    FilterResult(
                        flag="verify_engagement",
                        detail="engagement_type=unknown -> verify before applying",
                    ),
                )
            )
    else:
        allowed = [e.lower() for e in router.engagement_types_allow]
        if allowed and parsed.engagement_type.lower() not in allowed:
            results.append(
                (
                    "engagement_type",
                    FilterResult(
                        reason="engagement_type_not_allowed",
                        detail=f"engagement_type={parsed.engagement_type}",
                    ),
                )
            )

    # 2. exclusivity
    if parsed.exclusivity == "required":
        results.append(
            (
                "exclusivity",
                FilterResult(
                    reason="exclusivity_required",
                    detail="posting requires exclusive engagement",
                ),
            )
        )

    # 3. onsite_required
    if parsed.onsite_required is True:
        results.append(
            (
                "onsite_required",
                FilterResult(
                    reason="onsite_required",
                    detail="posting requires fixed on-site presence",
                ),
            )
        )

    # 4. country allow/deny
    allow = {c.upper() for c in router.countries_allow}
    deny = {c.upper() for c in router.countries_deny}
    countries = [c.upper() for c in parsed.countries_allowed]
    if allow and countries and not any(c in allow for c in countries):
        results.append(
            (
                "country",
                FilterResult(
                    reason="country_allow",
                    detail=f"countries {countries} not in allow list",
                ),
            )
        )
    elif deny and any(c in deny for c in countries):
        results.append(
            (
                "country",
                FilterResult(
                    reason="country_deny",
                    detail=f"country {countries} in deny list",
                ),
            )
        )

    # 5. overlap
    pw = posting_window(parsed)
    if pw is not None:
        ro = parsed.required_overlap
        assert ro is not None
        tz = str(ro["tz"])
        hours = overlap_hours(principal_tz, principal_window, tz, pw, reference)
        if hours < min_overlap_hours:
            results.append(
                (
                    "overlap",
                    FilterResult(
                        reason="overlap_below_min",
                        detail=f"overlap {hours:.1f}h < min {min_overlap_hours}h",
                    ),
                )
            )
    else:
        # Posting timezone unknown -> keep with flag (spec §11.3 filter 5).
        results.append(
            (
                "overlap",
                FilterResult(
                    flag="overlap_unknown",
                    detail="posting timezone unknown -> verify overlap",
                ),
            )
        )

    # 6. compensation
    if normalized_comp is not None:
        hours_week = parsed.hours_per_week
        mean_hours = (
            (hours_week[0] + hours_week[1]) / 2.0 if hours_week else None
        )
        # Reject when the whole band is under the floor. The spec's hours
        # exception (allow_below_floor_if_hours_leq) applies when the posting
        # is light enough that a lower monthly rate is acceptable.
        if normalized_comp.usd_max_month < router.rate_floor_usd_month:
            exception_ok = (
                router.allow_below_floor_if_hours_leq is not None
                and mean_hours is not None
                and mean_hours < router.allow_below_floor_if_hours_leq
            )
            if not exception_ok:
                results.append(
                    (
                        "compensation",
                        FilterResult(
                            reason="comp_below_floor",
                            detail=(
                                f"comp max ${normalized_comp.usd_max_month:.0f}/mo "
                                f"< floor ${router.rate_floor_usd_month:.0f}/mo"
                            ),
                        ),
                    )
                )
    else:
        # Unknown compensation: if the posting demands high hours (> exception
        # threshold), assume it's below floor rather than just flagging it.
        hours_week = parsed.hours_per_week
        mean_hours = (
            (hours_week[0] + hours_week[1]) / 2.0 if hours_week else None
        )
        if (
            mean_hours is not None
            and router.allow_below_floor_if_hours_leq is not None
            and mean_hours >= router.allow_below_floor_if_hours_leq
        ):
            results.append(
                (
                    "compensation",
                    FilterResult(
                        reason="comp_below_floor",
                        detail=(
                            f"comp unknown but hours {mean_hours:.0f}/wk "
                            f">= exception threshold "
                            f"{router.allow_below_floor_if_hours_leq:.0f}/wk "
                            f"-> assume below floor"
                        ),
                    ),
                )
            )
        else:
            results.append(
                (
                    "compensation",
                    FilterResult(
                        flag="ask_rate",
                        detail="compensation unknown -> ask at interview",
                    ),
                )
            )

    # 7. ai_tools_policy
    if parsed.ai_tools_policy == "forbidden":
        results.append(
            (
                "ai_tools",
                FilterResult(
                    reason="ai_tools_forbidden",
                    detail="posting forbids AI tools",
                ),
            )
        )

    # 8. red-flag blocklist
    flagged: list[str] = []
    for rf in parsed.red_flags:
        rf_l = rf.lower()
        for reason, patterns in RED_FLAG_PATTERNS.items():
            if reason in flagged:
                continue
            if any(p in rf_l for p in patterns):
                flagged.append(reason)
    for reason in flagged:
        results.append(
            (
                "red_flag",
                FilterResult(reason=f"red_flag_{reason}", detail=f"red flag: {reason}"),
            )
        )

    return results


__all__ = [
    "DEFAULT_POSTING_WINDOW",
    "RED_FLAG_PATTERNS",
    "FilterResult",
    "overlap_hours",
    "run_hard_filters",
]
