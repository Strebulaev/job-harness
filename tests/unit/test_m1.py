"""M1 unit tests: settings, profile validation, state machine, hashing, structured output."""

from __future__ import annotations

import pytest

from jobharness.db.state_machine import (
    IllegalTransition,
    assert_transition,
)
from jobharness.llm.hashing import request_hash
from jobharness.llm.structured import StructuredOutputError, extract_json
from jobharness.schemas.profile import (
    Profile,
    lint_profile,
    load_profile,
    validate_profile,
)
from jobharness.settings import Settings


# ---------------------------------------------------------------- settings
def test_settings_loads_example(tmp_path):
    cfg = Settings.from_yaml("config/config.example.yaml")
    assert cfg.llm.provider in ("anthropic", "fake")
    assert cfg.router.rate_floor_usd_month <= cfg.router.rate_ceiling_usd_month
    assert cfg.send.autosend.enabled is False


def test_settings_unknown_key_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "paths": {"data_dir": "./data", "output_dir": "./data/out"},
                "llm": {
                    "provider": "fake",
                    "models": {
                        "parse": "m",
                        "compose": "m",
                        "judge": "m",
                        "classify": "m",
                    },
                    "temperature": {
                        "parse": 0,
                        "compose": 0,
                        "judge": 0,
                        "classify": 0,
                    },
                },
                "principal": {
                    "timezone": "Europe/Kiev",
                    "work_window_local": {"start": "09:00", "end": "18:00"},
                    "min_overlap_hours": 3,
                    "target_overlap_hours": 4,
                },
                "router": {
                    "min_score_to_apply": 65,
                    "rate_floor_usd_month": 2000,
                    "rate_ceiling_usd_month": 4000,
                    "engagement_types_allow": ["contractor"],
                },
                "send": {
                    "autosend": {"enabled": False},
                    "max_per_day": 20,
                    "min_gap_seconds": 90,
                    "quiet_hours_local": {"start": "21:00", "end": "07:00"},
                },
                "followups": {"schedule_business_days": [5], "max_followups": 2},
                "capacity": {
                    "max_total_hours_week": 40,
                    "max_active_contracts": 3,
                    "warn_at_utilization": 0.8,
                },
                "fx": {"fx_as_of": "2026-10-01", "rates": {"USD": 1.0}},
                "bogus_top_level_key": 1,
            }
        )


def test_settings_rate_floor_le_ceiling():
    from pydantic import ValidationError

    bad = {
        "paths": {"data_dir": "./data", "output_dir": "./data/out"},
        "llm": {
            "provider": "fake",
            "models": {"parse": "m", "compose": "m", "judge": "m", "classify": "m"},
            "temperature": {"parse": 0, "compose": 0, "judge": 0, "classify": 0},
        },
        "principal": {
            "timezone": "UTC",
            "work_window_local": {"start": "09:00", "end": "18:00"},
            "min_overlap_hours": 3,
            "target_overlap_hours": 4,
        },
        "router": {
            "min_score_to_apply": 65,
            "rate_floor_usd_month": 5000,
            "rate_ceiling_usd_month": 2000,
            "engagement_types_allow": ["contractor"],
        },
        "send": {
            "autosend": {"enabled": False},
            "max_per_day": 20,
            "min_gap_seconds": 90,
            "quiet_hours_local": {"start": "21:00", "end": "07:00"},
        },
        "followups": {"schedule_business_days": [5], "max_followups": 2},
        "capacity": {
            "max_total_hours_week": 40,
            "max_active_contracts": 3,
            "warn_at_utilization": 0.8,
        },
        "fx": {"fx_as_of": "2026-10-01", "rates": {"USD": 1.0}},
    }
    with pytest.raises(ValidationError):
        Settings.model_validate(bad)


# ---------------------------------------------------------------- profile
def test_profile_example_validates():
    p = load_profile("config/profile.example.yaml")
    errors = validate_profile(p)
    assert errors == [], errors


def test_profile_duplicate_id_rejected():
    raw = """
version: 1
identity:
  full_name: X
  email: x@x.com
  location: {city: C, country: US, timezone: UTC}
summary_facts:
  - {id: sum.1, text: a, tags: []}
experience:
  - id: exp.a
    employer_real: A
    employer_display_options: {full: A}
    title_real: T
    title_display_options: {exact: T}
    start: "2020-01"
    end: "2021-01"
    employment_type: full_time
    bullets:
      - {id: exp.a.b1, text: x, kind: hands_on}
      - {id: exp.a.b1, text: y, kind: hands_on}
"""
    import yaml

    p = Profile.model_validate(yaml.safe_load(raw))
    errors = validate_profile(p)
    assert any("duplicate fact id" in e for e in errors), errors


def test_profile_out_of_order_dates_rejected_by_pydantic():
    import yaml
    from pydantic import ValidationError

    raw = """
version: 1
identity:
  full_name: X
  email: x@x.com
  location: {city: C, country: US, timezone: UTC}
experience:
  - id: exp.a
    employer_real: A
    employer_display_options: {full: A}
    title_real: T
    title_display_options: {exact: T}
    start: "2021-01"
    end: "2020-01"
    employment_type: full_time
    bullets: []
"""
    with pytest.raises(ValidationError):
        Profile.model_validate(yaml.safe_load(raw))


def test_profile_overlapping_full_time_rejected():
    import yaml

    raw = """
version: 1
identity:
  full_name: X
  email: x@x.com
  location: {city: C, country: US, timezone: UTC}
experience:
  - id: exp.a
    employer_real: A
    employer_display_options: {full: A}
    title_real: T
    title_display_options: {exact: T}
    start: "2019-01"
    end: "2021-01"
    employment_type: full_time
    bullets: []
  - id: exp.b
    employer_real: B
    employer_display_options: {full: B}
    title_real: T
    title_display_options: {exact: T}
    start: "2020-01"
    end: "2022-01"
    employment_type: full_time
    bullets: []
"""
    p = Profile.model_validate(yaml.safe_load(raw))
    errors = validate_profile(p)
    assert any("overlapping full-time" in e for e in errors), errors


def test_profile_dangling_skill_ref_rejected():
    import yaml

    raw = """
version: 1
identity:
  full_name: X
  email: x@x.com
  location: {city: C, country: US, timezone: UTC}
experience:
  - id: exp.a
    employer_real: A
    employer_display_options: {full: A}
    title_real: T
    title_display_options: {exact: T}
    start: "2019-01"
    end: "2021-01"
    employment_type: full_time
    bullets:
      - {id: exp.a.b1, text: x, kind: hands_on}
skills:
  - id: skill.x
    name: X
    level: expert
    years: 5
    evidence_fact_ids: [exp.a.b999]
"""
    p = Profile.model_validate(yaml.safe_load(raw))
    errors = validate_profile(p)
    assert any("references unknown fact id" in e for e in errors), errors


def test_profile_lint_warns_on_unverifiable_metrics():
    p = load_profile("config/profile.example.yaml")
    warnings = lint_profile(p)
    # skill.kubernetes has no evidence_fact_ids -> weak warning
    assert any("skill.kubernetes" in w and "weak" in w for w in warnings), warnings


# ---------------------------------------------------------------- state machine
def test_job_legal_transition():
    assert_transition("new", "parsed", kind="job")
    assert_transition("parsed", "shortlisted", kind="job")
    assert_transition("shortlisted", "composed", kind="job")
    assert_transition("composed", "queued", kind="job")
    assert_transition("queued", "approved", kind="job")
    assert_transition("approved", "sent", kind="job")
    assert_transition("sent", "closed", kind="job")


def test_job_illegal_transition_new_to_sent():
    with pytest.raises(IllegalTransition):
        assert_transition("new", "sent", kind="job")


def test_application_illegal_transition_queued_to_sent():
    with pytest.raises(IllegalTransition):
        assert_transition("queued", "sent", kind="application")


def test_application_legal_path():
    assert_transition("queued", "approved", kind="application")
    assert_transition("approved", "sent", kind="application")
    assert_transition("sent", "replied", kind="application")
    assert_transition("replied", "offer", kind="application")
    assert_transition("offer", "accepted", kind="application")


# ---------------------------------------------------------------- hashing
def test_request_hash_deterministic():
    a = request_hash(
        model="m", prompt_version="v1", system="s", user="u", temperature=0.0
    )
    b = request_hash(
        model="m", prompt_version="v1", system="s", user="u", temperature=0.0
    )
    assert a == b
    assert len(a) == 64


def test_request_hash_changes_with_input():
    base = {"model": "m", "prompt_version": "v1", "system": "s", "user": "u", "temperature": 0.0}
    a = request_hash(**base)
    b = request_hash(**{**base, "user": "u2"})
    c = request_hash(**{**base, "temperature": 0.5})
    assert a != b
    assert a != c


# ---------------------------------------------------------------- structured
def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_prose():
    assert extract_json('Here is the result: {"a": 1} hope that helps') == {"a": 1}


def test_extract_json_non_object_raises():
    with pytest.raises(StructuredOutputError):
        extract_json('[1, 2, 3]')


def test_extract_json_no_object_raises():
    with pytest.raises(StructuredOutputError):
        extract_json("no json here")
