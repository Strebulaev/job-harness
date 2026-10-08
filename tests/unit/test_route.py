"""M3 tests: hard filters, overlap computation, scoring, archetype selection,
overqualification, and the router golden-set precision/recall gate.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from jobharness.parse.normalizers import normalize_compensation
from jobharness.route import scoring
from jobharness.route.filters import overlap_hours, run_hard_filters
from jobharness.route.golden import evaluate_router
from jobharness.route.overqualification import evaluate
from jobharness.route.router import route_job
from jobharness.schemas.archetype import Archetype, load_archetypes
from jobharness.schemas.jd import Compensation, JDParsed
from jobharness.schemas.positioning import Positioning
from jobharness.schemas.profile import load_profile
from jobharness.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "eval_data" / "golden_jobs"
CONFIG_EXAMPLE = REPO_ROOT / "config" / "config.example.yaml"
PROFILE_EXAMPLE = REPO_ROOT / "config" / "profile.example.yaml"
POSITIONING_EXAMPLE = REPO_ROOT / "config" / "positioning.example.yaml"
ARCHETYPES_DIR = REPO_ROOT / "config" / "archetypes"

TZ = "Europe/Kiev"
WINDOW = ("09:00", "18:00")


def _settings(**section_overrides: object) -> Settings:
    """``_settings(router={...})`` merges section-level overrides."""
    base = Settings.from_yaml(CONFIG_EXAMPLE)
    raw = base.model_dump()
    for section, values in section_overrides.items():
        assert isinstance(values, dict)
        raw[section] = {**raw[section], **values}
    return Settings.model_validate(raw)


def _pos(**overrides: object) -> Positioning:
    import yaml

    raw = yaml.safe_load(POSITIONING_EXAMPLE.read_text(encoding="utf-8"))
    raw.update(overrides)
    return Positioning.model_validate(raw)


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings.from_yaml("config/config.yaml")


@pytest.fixture(scope="module")
def profile():
    return load_profile(str(PROFILE_EXAMPLE))


@pytest.fixture(scope="module")
def positioning() -> Positioning:
    return _pos()


@pytest.fixture(scope="module")
def archetypes() -> dict[str, Archetype]:
    return load_archetypes(ARCHETYPES_DIR)


def _parsed(**overrides: object) -> JDParsed:
    raw: dict[str, object] = {"title": "Test Job"}
    raw.update(overrides)
    return JDParsed.model_validate(raw)


def _filters(p: JDParsed, s: Settings, norm=None):
    return run_hard_filters(
        p, norm, s.router, TZ, WINDOW, s.principal.min_overlap_hours
    )


# ---------------------------------------------------------------- filters
def test_employee_rejected(settings: Settings) -> None:
    p = _parsed(engagement_type="employee")
    results = _filters(p, settings)
    assert "engagement_type_employee" in [r.reason for _, r in results if r.reason]


def test_exclusivity_rejected(settings: Settings) -> None:
    p = _parsed(engagement_type="contractor", exclusivity="required")
    results = _filters(p, settings)
    assert "exclusivity_required" in [r.reason for _, r in results if r.reason]


def test_onsite_rejected(settings: Settings) -> None:
    p = _parsed(engagement_type="contractor", onsite_required=True)
    results = _filters(p, settings)
    assert "onsite_required" in [r.reason for _, r in results if r.reason]


def test_country_deny_rejected() -> None:
    s = _settings(router={"countries_deny": ["SG"], "countries_allow": []})
    p = _parsed(engagement_type="contractor", countries_allowed=["SG"])
    results = _filters(p, s)
    assert "country_deny" in [r.reason for _, r in results if r.reason]


def test_ai_forbidden_rejected(settings: Settings) -> None:
    p = _parsed(engagement_type="contractor", ai_tools_policy="forbidden")
    results = _filters(p, settings)
    assert "ai_tools_forbidden" in [r.reason for _, r in results if r.reason]


def test_red_flags_blocklisted(settings: Settings) -> None:
    p = _parsed(
        engagement_type="contractor",
        red_flags=["Unpaid trial week", "Equity only, no cash"],
    )
    results = _filters(p, settings)
    reasons = [r.reason for _, r in results if r.reason]
    assert "red_flag_unpaid_trial" in reasons
    assert "red_flag_equity_only" in reasons


def test_comp_below_floor_rejected(settings: Settings) -> None:
    p = _parsed(
        engagement_type="contractor",
        compensation={"min": 1800, "max": 1800, "currency": "USD", "period": "month"},
        hours_per_week=[15, 15],
    )
    norm = normalize_compensation(
        p.compensation, settings, hours_per_week=p.hours_per_week
    )
    results = _filters(p, settings, norm)
    assert "comp_below_floor" in [r.reason for _, r in results if r.reason]


def test_comp_below_floor_hours_exception(settings: Settings) -> None:
    """Spec §5 exception: below floor allowed when hours < 10 (strictly less)."""
    p = _parsed(
        engagement_type="contractor",
        compensation={"min": 1800, "max": 1800, "currency": "USD", "period": "month"},
        hours_per_week=[9.5, 9.5],
    )
    norm = normalize_compensation(
        p.compensation, settings, hours_per_week=p.hours_per_week
    )
    results = _filters(p, settings, norm)
    assert "comp_below_floor" not in [r.reason for _, r in results if r.reason]


def test_unknown_engagement_flags_verify(settings: Settings) -> None:
    p = _parsed(engagement_type="unknown")
    results = _filters(p, settings)
    assert "verify_engagement" in [r.flag for _, r in results if r.flag]


def test_unknown_comp_flags_ask_rate(settings: Settings) -> None:
    p = _parsed(engagement_type="contractor")
    results = _filters(p, settings)
    assert "ask_rate" in [r.flag for _, r in results if r.flag]


def test_overlap_below_min_rejected(settings: Settings) -> None:
    # Asia/Kathmandu (+05:45) 00:00-08:00 = 18:15-02:15 UTC;
    # principal 09:00-18:00 Europe/Kiev (+03:00) = 06:00-15:00 UTC -> 0h.
    p = _parsed(
        engagement_type="contractor",
        required_overlap={"tz": "Asia/Kathmandu", "start": "00:00", "end": "08:00"},
    )
    results = _filters(p, settings)
    assert "overlap_below_min" in [r.reason for _, r in results if r.reason]


# ---------------------------------------------------------------- overlap
def test_overlap_same_tz() -> None:
    assert overlap_hours("UTC", ("09:00", "18:00"), "UTC", ("09:00", "17:00")) == 8.0


def test_overlap_no_intersection() -> None:
    assert overlap_hours("UTC", ("00:00", "06:00"), "UTC", ("12:00", "18:00")) == 0.0


def test_overlap_cross_tz_eu_vs_us() -> None:
    # Europe/Berlin summer (CEST, +2) 09:00-18:00 = 07:00-16:00 UTC
    # America/New_York summer (EDT, -4) 09:00-18:00 = 13:00-22:00 UTC
    # overlap = 13:00-16:00 = 3h
    h = overlap_hours(
        "Europe/Berlin",
        ("09:00", "18:00"),
        "America/New_York",
        ("09:00", "18:00"),
        reference=datetime(2026, 6, 15),
    )
    assert h == pytest.approx(3.0)


def test_overlap_cross_tz_kiev_novosibirsk() -> None:
    # g06 golden case: Kiev (EET +03) 09:00-18:00 = 06:00-15:00 UTC;
    # Novosibirsk (+07) 10:00-19:00 = 03:00-12:00 UTC -> overlap 06:00-12:00 = 6h.
    h = overlap_hours(
        "Europe/Kiev",
        ("09:00", "18:00"),
        "Asia/Novosibirsk",
        ("10:00", "19:00"),
        reference=datetime(2026, 9, 12),
    )
    assert h == pytest.approx(6.0)


def test_overlap_full_containment() -> None:
    assert overlap_hours("UTC", ("09:00", "17:00"), "UTC", ("07:00", "18:00")) == 8.0


def test_overlap_dst_switching_days() -> None:
    # Windows that straddle a DST boundary must still be computed correctly.
    # Berlin winter (CET +1) 10:00-12:00 = 09:00-11:00 UTC;
    # Berlin summer (CEST +2) 10:00-12:00 = 08:00-10:00 UTC.
    winter = overlap_hours(
        "Europe/Berlin",
        ("10:00", "12:00"),
        "UTC",
        ("09:00", "10:00"),
        reference=datetime(2026, 1, 15),
    )
    summer = overlap_hours(
        "Europe/Berlin",
        ("10:00", "12:00"),
        "UTC",
        ("08:00", "09:00"),
        reference=datetime(2026, 7, 15),
    )
    assert winter == pytest.approx(1.0)
    assert summer == pytest.approx(1.0)


# ---------------------------------------------------------------- scoring
def test_rate_fit_in_band(settings: Settings) -> None:
    pos = _pos()
    comp = Compensation(min=2000, max=4000, currency="USD", period="month")
    norm = normalize_compensation(comp, settings)
    s, _ = scoring.rate_fit_score(norm, pos)
    assert s == pytest.approx(20.0)


def test_rate_fit_partial_band(settings: Settings) -> None:
    pos = _pos()
    comp = Compensation(min=3000, max=4000, currency="USD", period="month")
    norm = normalize_compensation(comp, settings)
    s, _ = scoring.rate_fit_score(norm, pos)
    assert s == pytest.approx(15.0)


def test_rate_fit_unknown_neutral() -> None:
    pos = _pos()
    s, _ = scoring.rate_fit_score(None, pos)
    assert s == pytest.approx(10.0)  # unknown -> neutral


def test_stack_match_perfect_and_zero(profile) -> None:
    good = _parsed(must_have=["python"], tech_stack=["python"])
    s, _ = scoring.stack_match_score(good, profile)
    assert s == pytest.approx(30.0)
    bad = _parsed(must_have=["quantum-weaving"], tech_stack=["quantum-weaving"])
    s2, _ = scoring.stack_match_score(bad, profile)
    assert s2 < 5.0


def test_tz_overlap_scores() -> None:
    assert scoring.tz_overlap_score(4.0, 3.0, 4.0)[0] == pytest.approx(15.0)
    assert scoring.tz_overlap_score(3.5, 3.0, 4.0)[0] == pytest.approx(12.5)
    assert scoring.tz_overlap_score(2.0, 3.0, 4.0)[0] == 0.0
    assert scoring.tz_overlap_score(None, 3.0, 4.0)[0] == pytest.approx(7.5)


def test_engagement_fit() -> None:
    assert scoring.engagement_fit_score(_parsed(engagement_type="b2b"))[0] == 10.0
    assert scoring.engagement_fit_score(_parsed(engagement_type="unknown"))[0] == 5.0


def test_quality_named_contact() -> None:
    p = _parsed(
        company="Acme",
        application_email="jobs@acme.example",
        application_method="email",
        must_have=["python", "sql", "api"],
    )
    s, _ = scoring.quality_score(p)
    assert s == pytest.approx(10.0)


def test_overqualification_penalty_above_ceiling() -> None:
    pos = _pos()
    s = _settings()
    norm = normalize_compensation(
        Compensation(min=4500, max=6000, currency="USD", period="month"), s
    )
    penalty = scoring.overqualification_penalty(norm, pos)
    assert penalty > 0.0
    penalty_low = scoring.overqualification_penalty(
        normalize_compensation(
            Compensation(min=2500, max=3500, currency="USD", period="month"), s
        ),
        pos,
    )
    assert penalty_low == 0.0


# ---------------------------------------------------------------- archetype
def test_select_archetypes_positive_labels(archetypes: dict[str, Archetype]) -> None:
    """The six positive golden jobs each pick their labeled archetype."""
    cases = {
        "g01_rag_remote_ok": "a_ai_llm_engineer",
        "g02_backend_himalayas": "b_backend_contractor",
        "g09_automation_positive": "c_automation_integration",
        "g10_platform_devops_positive": "d_platform_devops_light",
        "g11_advisor_positive": "e_technical_advisor",
        "g12_fullstack_mvp_positive": "f_fullstack_mvp",
    }
    for stem, want in cases.items():
        data = json.loads((GOLDEN_DIR / f"{stem}.json").read_text(encoding="utf-8"))
        label = dict(data["expected_jd_parsed"])
        parsed = JDParsed.model_validate(label)
        top = scoring.select_archetypes(parsed, archetypes)
        assert top[0][0] == want, f"{stem}: got {top[0]}, want {want}"


# ---------------------------------------------------------------- overqualification
def test_overqualification_senior_ic_vs_staff(positioning: Positioning) -> None:
    # senior_ic(3) - staff(4) = -1 -> no flip
    assert evaluate(positioning, "staff").handson_focus is False
    # senior_ic(3) - senior(3) = 0 -> no flip
    assert evaluate(positioning, "senior").handson_focus is False
    # staff_ic(4) - senior(3) = 1 -> no flip
    staff = _pos(target_level="staff_ic")
    assert evaluate(staff, "senior").handson_focus is False


def test_overqualification_principal_flips(positioning: Positioning) -> None:
    # posting 'mid' (2) vs principal senior_ic (3): gap 1 -> no flip
    assert evaluate(positioning, "mid").handson_focus is False
    # a staff_ic principal vs mid posting: gap 2 -> flip
    staff = _pos(target_level="staff_ic")
    assert evaluate(staff, "mid").handson_focus is True


def test_positioning_applied_shape(positioning: Positioning) -> None:
    staff = _pos(target_level="staff_ic")
    oq = evaluate(staff, "mid")
    block = oq.positioning_applied()["overqualification"]
    assert block["handson_focus"] is True
    assert block["gap"] == 2


# ---------------------------------------------------------------- router golden set
def test_router_golden_precision_recall(
    profile,
    positioning: Positioning,
    archetypes: dict[str, Archetype],
    settings: Settings,
) -> None:
    """M3 acceptance: precision >= 0.85 and recall >= 0.80 on the 30 labels."""
    metrics = evaluate_router(GOLDEN_DIR, profile, positioning, archetypes, settings)
    print(
        f"router golden: precision={metrics.precision:.3f} "
        f"recall={metrics.recall:.3f} arch_acc={metrics.archetype_accuracy:.3f}"
    )
    assert metrics.precision >= 0.85, (
        f"precision {metrics.precision:.3f} < 0.85; "
        f"FPs={[r.job_id for r in metrics.results if r.fp]}"
    )
    assert metrics.recall >= 0.80, (
        f"recall {metrics.recall:.3f} < 0.80; "
        f"FNs={[r.job_id for r in metrics.results if r.fn]}"
    )
    assert metrics.archetype_accuracy >= 0.85, (
        f"archetype accuracy {metrics.archetype_accuracy:.3f}; "
        f"wrong: {metrics.wrong_archetype}"
    )


def test_router_reject_reasons_match_labels(
    profile,
    positioning: Positioning,
    archetypes: dict[str, Archetype],
    settings: Settings,
) -> None:
    """Every labeled rejection reason must be produced by the router."""
    metrics = evaluate_router(GOLDEN_DIR, profile, positioning, archetypes, settings)
    missing: list[tuple[str, str]] = []
    for r in metrics.results:
        for want in r.label_reject_reasons:
            if want not in r.predicted_reject_reasons:
                missing.append((r.job_id, want))
    assert not missing, f"missing reject reasons: {missing}"


def test_route_job_end_to_end_shortlisted(
    profile,
    positioning: Positioning,
    archetypes: dict[str, Archetype],
    settings: Settings,
) -> None:
    data = json.loads((GOLDEN_DIR / "g01_rag_remote_ok.json").read_text(encoding="utf-8"))
    label = dict(data["expected_jd_parsed"])
    parsed = JDParsed.model_validate(label)
    from jobharness.parse.jd_parser import verify_evidence_spans

    parsed, _ = verify_evidence_spans(parsed, data["jd_raw"])
    norm = normalize_compensation(
        parsed.compensation, settings, hours_per_week=parsed.hours_per_week
    )
    result = route_job(
        parsed, profile, positioning, archetypes, settings, normalized_comp=norm
    )
    assert not result.rejected
    assert result.shortlisted
    assert result.archetype == "a_ai_llm_engineer"
    assert result.score is not None
    assert result.score >= settings.router.min_score_to_apply
