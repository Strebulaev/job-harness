"""M2-1 test: the 30 golden jobs are present and structurally valid."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validate_golden_jobs.py"
GOLDEN_DIR = REPO_ROOT / "eval_data" / "golden_jobs"


def test_golden_jobs_count_at_least_30():
    files = list(GOLDEN_DIR.glob("*.json"))
    # Exclude expected_downgrades.json and baseline.json
    files = [f for f in files if f.stem not in ("expected_downgrades", "baseline")]
    assert len(files) >= 30, f"expected >= 30 golden jobs, found {len(files)}"


def test_golden_jobs_validate():
    """Run the one-off validator; every file must pass schema + span checks."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, f"validator failed:\n{proc.stdout}\n{proc.stderr}"


def test_golden_jobs_apply_archetype_consistency():
    """Every file: apply=yes requires an archetype; apply=no requires reasons."""
    import json

    for path in sorted(
        p for p in GOLDEN_DIR.glob("*.json")
        if p.stem not in ("expected_downgrades", "baseline")
    ):
        data = json.loads(path.read_text(encoding="utf-8"))
        apply = data["expected_apply"]
        arch = data.get("expected_archetype")
        reasons = data.get("expected_reject_reasons", [])
        if apply == "yes":
            assert arch is not None, f"{path.name}: apply=yes but no archetype"
        if apply == "no":
            assert reasons, f"{path.name}: apply=no but no reject reasons"
