"""Generate FakeProvider fixtures for the 30 golden jobs (M2-3).

For each file in ``eval_data/golden_jobs/*.json``, compute the
``request_hash`` of the exact request ``parse_jd`` issues (model
``fake-parse-v1``, prompt version ``v1``, temperature 0.0, schema
``JDParsed``, system prompt = the jd_parse v1 body, user = the wrapped
JD) and write ``tests/fixtures/llm/<hash>.json`` containing the
fixture ``JDParsed`` object.

The fixture object is built from ``expected_jd_parsed`` with spans
added for any non-unknown field that lacks one in the golden label:

- a span is a verbatim substring of ``jd_raw`` found via a
  deterministic token search (the first line containing a distinctive
  token from the field value);
- if no line backs the value, the field is downgraded to unknown/empty
  (the post-check would do the same, so the fixture must match it);
- stale spans on unknown fields are dropped.

Usage: ``uv run python scripts/gen_parse_fixtures.py [--check]``
``--check`` exits non-zero if a fixture is missing or stale instead of
writing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from jobharness.llm.hashing import request_hash
from jobharness.llm.prompts import load_system_prompt
from jobharness.parse.jd_parser import build_user_message
from jobharness.schemas.jd import JDParsed

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "eval_data" / "golden_jobs"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "llm"
SIDECAR = GOLDEN_DIR / "expected_downgrades.json"

MODEL = "fake-parse-v1"
PROMPT_VERSION = "v1"
TEMPERATURE = 0.0
SCHEMA_NAME = "JDParsed"

_STOPWORDS = frozenset({"the", "and", "a", "an", "in", "of", "to", "with", "or", "unknown"})


def _norm_ws(s: str) -> str:
    return " ".join(s.lower().split())


def _find_line_with_tokens(jd_raw: str, tokens: list[str]) -> str | None:
    """Return the first line of ``jd_raw`` that contains at least one of
    ``tokens`` (case-insensitive). Deterministic; returns None if no line
    matches."""
    if not tokens:
        return None
    for line in jd_raw.splitlines():
        line_norm = _norm_ws(line)
        if any(_norm_ws(t) in line_norm for t in tokens):
            return line.strip()
    return None


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _STOPWORDS]


def _derive_span(field: str, value: Any, jd_raw: str) -> str | None:
    """Pick a verbatim substring of ``jd_raw`` that backs ``field``.

    Returns None when no line contains a distinctive token — the caller
    then downgrades the field rather than fabricating a span.
    """
    if isinstance(value, list):
        if not value:
            return None
        words = _words(str(value[0]))
        return _find_line_with_tokens(jd_raw, words[:3])
    if isinstance(value, bool):
        tokens = (
            ["on site", "onsite", "office"]
            if value
            else ["remote", "no onsite", "no exclusivity"]
        )
        return _find_line_with_tokens(jd_raw, tokens)
    if isinstance(value, (int, float)):
        return _find_line_with_tokens(jd_raw, [f"{value:g}"])
    if isinstance(value, dict):
        tokens = [str(v) for k, v in value.items() if k in ("tz", "start", "end")]
        return _find_line_with_tokens(jd_raw, tokens)
    if isinstance(value, str):
        words = _words(value)
        return _find_line_with_tokens(jd_raw, words[:3])
    return None


def _downgrade(obj: dict[str, Any], field: str) -> None:
    """Set a field to its unknown/empty value, mirroring the parser."""
    if field == "onsite_required":
        obj[field] = None
    elif field in ("seniority", "engagement_type", "exclusivity", "remote_policy",
                   "ai_tools_policy", "subcontracting_policy", "application_method"):
        obj[field] = "unknown"
    elif field in ("countries_allowed", "must_have", "nice_to_have", "tech_stack",
                   "responsibilities", "red_flags"):
        obj[field] = []
    elif field in ("timezone_requirements", "required_overlap",
                   "hours_per_week", "compensation"):
        obj[field] = None
    else:
        raise ValueError(f"unknown evidence category: {field!r}")


_EVIDENCE_FIELDS = (
    "seniority",
    "engagement_type",
    "exclusivity",
    "remote_policy",
    "onsite_required",
    "countries_allowed",
    "timezone_requirements",
    "required_overlap",
    "hours_per_week",
    "compensation",
    "must_have",
    "nice_to_have",
    "tech_stack",
    "responsibilities",
    "ai_tools_policy",
    "subcontracting_policy",
    "red_flags",
    "application_method",
)


def _is_unknown(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v == "unknown"
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def build_fixture_object(
    expected: dict[str, Any], jd_raw: str
) -> tuple[dict[str, Any], list[str]]:
    """Build the fixture object from a golden label.

    Returns ``(obj, downgraded_fields)`` where ``downgraded_fields`` lists
    the fields whose hand-labeled value could not be backed by a verbatim
    substring of ``jd_raw`` (the post-check would downgrade them, so the
    fixture must match).
    """
    obj: dict[str, Any] = dict(expected)
    spans: dict[str, str] = dict(obj.get("evidence_spans", {}))
    norm_raw = _norm_ws(jd_raw)
    downgraded: list[str] = []

    for field in _EVIDENCE_FIELDS:
        if field not in obj:
            continue
        value = obj[field]
        if _is_unknown(value):
            spans.pop(field, None)
            continue
        if field in spans:
            if _norm_ws(spans[field]) in norm_raw:
                continue
            spans.pop(field, None)
        derived = _derive_span(field, value, jd_raw)
        if derived is not None and _norm_ws(derived) in norm_raw:
            spans[field] = derived
        else:
            downgraded.append(field)
            _downgrade(obj, field)

    obj["evidence_spans"] = spans
    JDParsed.model_validate(obj)
    return obj, downgraded


def compute_hash(jd_raw: str) -> str:
    system = load_system_prompt("jd_parse", PROMPT_VERSION)
    user = build_user_message(jd_raw)
    return request_hash(
        model=MODEL,
        prompt_version=PROMPT_VERSION,
        system=system,
        user=user,
        temperature=TEMPERATURE,
        schema_name=SCHEMA_NAME,
    )


def fixture_payload(obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": obj,
        "meta": {
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": 0,
            "cost_usd": 0.0,
        },
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail on missing/stale fixtures")
    args = ap.parse_args(argv)

    files = sorted(
        p for p in GOLDEN_DIR.glob("*.json") if p.stem != "expected_downgrades"
    )
    if len(files) < 30:
        print(f"FAIL: expected >= 30 golden jobs, found {len(files)}")
        return 1

    problems: list[str] = []
    written = 0
    downgrades: dict[str, list[str]] = {}
    for path in files:
        with path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        jd_raw = str(data["jd_raw"])
        obj, downgraded = build_fixture_object(dict(data["expected_jd_parsed"]), jd_raw)
        if downgraded:
            downgrades[path.stem] = sorted(downgraded)
        rh = compute_hash(jd_raw)
        target = FIXTURES_DIR / f"{rh}.json"
        text = json.dumps(fixture_payload(obj), indent=2, ensure_ascii=False,
                         sort_keys=True) + "\n"

        if args.check:
            if not target.exists():
                problems.append(f"missing fixture for {path.name}: {target.name}")
            elif target.read_text(encoding="utf-8") != text:
                problems.append(f"stale fixture for {path.name}: {target.name}")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written += 1

    # Sidecar: which fields the post-check downgrades per golden job. The
    # test (test_jd_parser.py) asserts the parser's downgrades match this
    # exactly, so the golden labels + sidecar fully specify expected output.
    SIDECAR.write_text(
        json.dumps(downgrades, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if downgrades:
        print(f"NOTE: {len(downgrades)} golden jobs have downgraded fields (see {SIDECAR.name}):")
        for stem, fields in sorted(downgrades.items()):
            print(f"  - {stem}: {fields}")

    if args.check:
        if problems:
            print(f"FAIL: {len(problems)} fixture problems:")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(f"OK: {len(files)} fixtures present and current")
        return 0

    print(f"OK: wrote {written} fixtures to {FIXTURES_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
