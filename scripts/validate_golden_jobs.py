"""Validate golden JDs (M2-1 done-when) against the JDParsed schema.

Each file in ``eval_data/golden_jobs/`` is one JSON object:
- ``jd_raw`` (str): the full JD text
- ``expected_jd_parsed``: a PARTIAL ``JDParsed`` — only the fields that MUST
  be non-"unknown" are present; every provided field must type-check against
  the schema (``extra='allow'`` is NOT used: unknown keys are an error)
- ``expected_apply``: "yes" | "no"
- ``expected_archetype``: one of the six archetype ids, or null when rejected
- ``expected_reject_reasons``: list (may be empty)
- ``id``, ``source``, ``url``, ``notes``: metadata

Exit 0 when every file validates; non-zero with a per-file error list.
Run: ``uv run python scripts/validate_golden_jobs.py``
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "eval_data" / "golden_jobs"

ARCHETYPE_IDS = {
    "a_ai_llm_engineer",
    "b_backend_contractor",
    "c_automation_integration",
    "d_platform_devops_light",
    "e_technical_advisor",
    "f_fullstack_mvp",
}

COMP_PERIODS = {"hour", "month", "year", "project"}


class CompensationPartial(BaseModel):
    min: float
    max: float
    currency: str
    period: str

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> CompensationPartial:
        comp = cls.model_validate(data)
        if comp.period not in COMP_PERIODS:
            raise ValueError(f"period must be one of {sorted(COMP_PERIODS)}")
        if comp.max < comp.min:
            raise ValueError(f"max < min: {comp.max} < {comp.min}")
        return comp


class ExpectedJDParsed(BaseModel):
    """Partial JDParsed: only the MUST-be-known fields are present."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    company: str | None = None
    seniority: str | None = None
    engagement_type: str | None = None
    exclusivity: str | None = None
    remote_policy: str | None = None
    onsite_required: bool | None = None
    countries_allowed: list[str] | None = None
    timezone_requirements: str | None = None
    required_overlap: dict[str, Any] | None = None
    hours_per_week: Sequence[float] | None = None
    compensation: dict[str, Any] | None = None
    must_have: list[str] | None = None
    nice_to_have: list[str] | None = None
    tech_stack: list[str] | None = None
    responsibilities: list[str] | None = None
    ai_tools_policy: str | None = None
    subcontracting_policy: str | None = None
    red_flags: list[str] | None = None
    application_method: str | None = None
    application_email: str | None = None
    evidence_spans: dict[str, str] | None = None


SENIORITIES = {"intern", "junior", "mid", "senior", "staff", "principal", "lead", "unknown"}
CATS = {
    "engagement_type": {"employee", "contractor", "b2b", "freelance", "project", "unknown"},
    "exclusivity": {"required", "preferred", "none", "unknown"},
    "remote_policy": {"remote", "hybrid", "onsite", "unknown"},
    "ai_tools_policy": {"allowed", "forbidden", "unknown"},
    "subcontracting_policy": {"allowed", "forbidden", "unknown"},
    "application_method": {"email", "platform", "form", "unknown"},
}


def load_expected(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data


def validate_file(path: Path) -> list[str]:
    """Return a list of error strings for one golden job file."""
    errors: list[str] = []
    try:
        data = load_expected(path)
    except json.JSONDecodeError as e:
        return [f"JSON parse error: {e}"]

    for key in ("id", "source", "url", "jd_raw", "expected_jd_parsed", "expected_apply"):
        if key not in data:
            errors.append(f"missing top-level key: {key}")
    if errors:
        return errors

    if data["expected_apply"] not in ("yes", "no"):
        errors.append(f"expected_apply must be 'yes' or 'no', got {data['expected_apply']!r}")

    arch = data.get("expected_archetype")
    if arch is not None and arch not in ARCHETYPE_IDS:
        errors.append(f"expected_archetype {arch!r} not in {sorted(ARCHETYPE_IDS)}")

    reasons = data.get("expected_reject_reasons")
    if reasons is not None and not isinstance(reasons, list):
        errors.append("expected_reject_reasons must be a list")

    # Apply label vs reject-reasons consistency:
    if data["expected_apply"] == "no" and not reasons:
        errors.append("expected_apply='no' but expected_reject_reasons is empty")
    if data["expected_apply"] == "yes" and arch is None:
        errors.append("expected_apply='yes' but expected_archetype is null")

    raw = data.get("jd_raw", "")
    if not raw or not raw.strip():
        errors.append("jd_raw is empty")

    try:
        expected = ExpectedJDParsed(**data["expected_jd_parsed"])
    except (ValidationError, TypeError) as e:
        errors.append(f"expected_jd_parsed failed schema validation: {e}")
        return errors

    if expected.seniority is not None and expected.seniority not in SENIORITIES:
        errors.append(f"seniority {expected.seniority!r} not in {sorted(SENIORITIES)}")

    for field, allowed in CATS.items():
        value = getattr(expected, field)
        if value is not None and value not in allowed:
            errors.append(f"{field}={value!r} not in {sorted(allowed)}")

    if expected.compensation is not None:
        try:
            CompensationPartial.from_data(expected.compensation)
        except (ValidationError, ValueError) as e:
            errors.append(f"compensation invalid: {e}")

    hpw = expected.hours_per_week
    if hpw is not None:
        lo, hi = float(hpw[0]), float(hpw[1])
        if not (0 < lo <= hi):
            errors.append(f"hours_per_week must be 0 < lo <= hi, got {hpw}")

    if expected.countries_allowed is not None:
        for c in expected.countries_allowed:
            if len(c) != 2 or not c.isalpha() or not c.isupper():
                errors.append(f"countries_allowed entry {c!r} is not ISO-3166 alpha-2")

    # Evidence spans: every non-"unknown" categorical field SHOULD have a span,
    # and each span MUST be a substring of jd_raw (case-insensitive,
    # whitespace-normalized) — the parser post-check (spec §10) enforces the
    # same rule on LLM output.
    norm_raw = " ".join(raw.lower().split())
    for field in CATS:
        value = getattr(expected, field)
        if value in ("unknown", None):
            continue
        spans = expected.evidence_spans or {}
        if field not in spans:
            errors.append(f"field {field}={value!r} is non-unknown but has no evidence_span")
            continue
        span_norm = " ".join(spans[field].lower().split())
        if span_norm not in norm_raw:
            errors.append(
                f"evidence span for {field} ({spans[field]!r}) is not a substring of jd_raw"
            )

    return errors


def main() -> int:
    files = sorted(p for p in GOLDEN_DIR.glob("*.json") if p.stem not in ("expected_downgrades", "baseline"))
    if len(files) < 30:
        print(f"FAIL: expected >= 30 golden jobs, found {len(files)}")
        return 1

    all_errors: dict[str, list[str]] = {}
    for path in files:
        errs = validate_file(path)
        if errs:
            all_errors[path.name] = errs

    if all_errors:
        print(f"FAIL: {len(all_errors)}/{len(files)} golden job files invalid:")
        for name, errs in sorted(all_errors.items()):
            print(f"  {name}:")
            for e in errs:
                print(f"    - {e}")
        return 1

    print(f"OK: {len(files)} golden jobs validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
