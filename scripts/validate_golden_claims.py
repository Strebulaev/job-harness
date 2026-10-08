"""Validate ``eval_data/golden_claims/*.json`` (plan step 2.1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

GOLDEN = Path(__file__).resolve().parents[1] / "eval_data" / "golden_claims"
LABELS = {"supported", "partial", "unsupported"}
KINDS = {"number_inflation", "added_tech", "title_change", "date_shift"}


def validate(path: Path) -> list[str]:
    errs: list[str] = []
    data = json.loads(path.read_text(encoding="utf-8"))
    if set(data) != {"snippet", "cited_fact_ids", "expected_label", "fabrication_type"}:
        errs.append(f"{path.name}: unexpected keys {sorted(data)}")
        return errs
    if not isinstance(data["snippet"], str) or not data["snippet"].strip():
        errs.append(f"{path.name}: empty snippet")
    if not data["cited_fact_ids"] or not all(isinstance(i, str) for i in data["cited_fact_ids"]):
        errs.append(f"{path.name}: cited_fact_ids must be a non-empty list of strings")
    if data["expected_label"] not in LABELS:
        errs.append(f"{path.name}: bad label {data['expected_label']!r}")
    kind = data["fabrication_type"]
    if kind is not None and kind not in KINDS:
        errs.append(f"{path.name}: bad fabrication_type {kind!r}")
    if (kind is None) != (data["expected_label"] == "supported"):
        errs.append(f"{path.name}: label and fabrication_type disagree")
    return errs


def main() -> int:
    errors: list[str] = []
    for p in sorted(GOLDEN.glob("*.json")):
        errors += validate(p)
    for e in errors:
        print(e, file=sys.stderr)
    print(f"{len(list(GOLDEN.glob('*.json')))} files, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
