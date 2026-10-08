"""Step 2.1: golden claims set structure and detector recall."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "eval_data" / "golden_claims"
sys.path.insert(0, str(ROOT / "scripts"))

from validate_golden_claims import validate  # noqa: E402


def _files() -> list[Path]:
    return sorted(GOLDEN.glob("*.json"))


def test_at_least_60_files_all_valid() -> None:
    files = _files()
    assert len(files) >= 60
    errors = [e for p in files for e in validate(p)]
    assert errors == []


def test_fabrication_coverage() -> None:
    kinds = Counter(
        json.loads(p.read_text())["fabrication_type"] for p in _files()
    )
    kinds.pop(None, None)
    assert sum(kinds.values()) >= 15
    assert set(kinds) == {"number_inflation", "added_tech", "title_change", "date_shift"}
    assert all(n >= 3 for n in kinds.values())
