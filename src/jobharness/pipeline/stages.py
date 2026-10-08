"""Per-job pipeline stages shared by the cycle runner (parse, route, status moves)."""

from __future__ import annotations

import json

from jobharness.db.models import Job
from jobharness.db.session import get_session
from jobharness.db.state_machine import assert_transition
from jobharness.llm.prompt_versions import default_version
from jobharness.llm.provider import LLMProvider
from jobharness.parse.jd_parser import parse_jd
from jobharness.parse.normalizers import UnknownCurrencyError, normalize_compensation
from jobharness.route.router import route_job
from jobharness.schemas.archetype import Archetype
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import Positioning
from jobharness.schemas.profile import Profile
from jobharness.settings import Settings


def move(job_id: int, *targets: str) -> None:
    """Walk ``job_id`` through ``targets`` in order via the state machine."""
    with get_session()() as s:
        row = s.get(Job, job_id)
        assert row is not None
        for t in targets:
            assert_transition(row.status, t, kind="job")
            row.status = t
        s.commit()


async def parse_job(job_id: int, provider: LLMProvider, settings: Settings) -> tuple[bool, str]:
    """Parse one ``new`` job (mirrors ``jh parse run``). Returns (ok, detail)."""
    with get_session()() as s:
        job = s.get(Job, job_id)
        assert job is not None
        jd_raw = job.jd_raw or ""
    model = settings.llm.models.parse
    try:
        result = await parse_jd(
            jd_raw, provider, model=model, temperature=settings.llm.temperature.parse
        )
        comp_confidence = comp_min = comp_max = None
        if result.parsed.compensation is not None:
            norm = normalize_compensation(
                result.parsed.compensation, settings, hours_per_week=result.parsed.hours_per_week
            )
            comp_confidence, comp_min, comp_max = (
                norm.confidence, norm.usd_min_month, norm.usd_max_month
            )
    except Exception as e:
        reason = f"parse_failed: {type(e).__name__}: {str(e)[:120]}"
        with get_session()() as s:
            row = s.get(Job, job_id)
            assert row is not None
            assert_transition(row.status, "rejected", kind="job")
            row.status = "rejected"
            row.reject_reasons_json = json.dumps([reason])
            s.commit()
        return False, reason
    p = result.parsed
    with get_session()() as s:
        row = s.get(Job, job_id)
        assert row is not None
        row.jd_parsed_json = json.dumps(p.model_dump(), sort_keys=True)
        row.parse_model = model
        row.parse_prompt_version = default_version("jd_parse")
        row.engagement_type = p.engagement_type
        row.remote_policy = p.remote_policy
        row.exclusivity = 1 if p.exclusivity == "required" else 0 if p.exclusivity == "none" else None
        row.ai_policy = p.ai_tools_policy
        row.subcontracting_policy = p.subcontracting_policy
        row.comp_confidence = comp_confidence
        row.comp_min_usd_month = comp_min
        row.comp_max_usd_month = comp_max
        if p.company:
            row.company = p.company
        if p.title:
            row.title = p.title
        assert_transition(row.status, "parsed", kind="job")
        row.status = "parsed"
        s.commit()
    return True, "ok"


def route_one(
    job_id: int,
    profile: Profile,
    positioning: Positioning,
    archetypes: dict[str, Archetype],
    settings: Settings,
) -> str:
    """Route one ``parsed`` job (mirrors ``jh route run``). Returns the new status."""
    with get_session()() as s:
        job = s.get(Job, job_id)
        assert job is not None
        parsed = JDParsed.model_validate_json(job.jd_parsed_json or "{}")
    norm = None
    if parsed.compensation is not None:
        try:
            norm = normalize_compensation(
                parsed.compensation, settings, hours_per_week=parsed.hours_per_week
            )
        except UnknownCurrencyError:
            norm = None
    result = route_job(parsed, profile, positioning, archetypes, settings, normalized_comp=norm)
    target = "rejected" if result.rejected else "shortlisted"
    with get_session()() as s:
        row = s.get(Job, job_id)
        assert row is not None
        assert_transition(row.status, target, kind="job")
        row.status = target
        row.score = result.score
        row.score_breakdown_json = json.dumps(result.breakdown or {}, sort_keys=True)
        row.archetype = result.archetype
        row.reject_reasons_json = json.dumps(
            [*result.reject_reasons, *(f"flag:{f}" for f in result.flags)]
        )
        row.overlap_hours = result.overlap_hours
        s.commit()
    return target


__all__ = ["move", "parse_job", "route_one"]
