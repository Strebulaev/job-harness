"""Router golden-set evaluation (spec §13.3, M3-2).

Runs the router over ``eval_data/golden_jobs/*.json`` and compares the
result against each file's labels (``expected_apply``,
``expected_reject_reasons``, ``expected_archetype``).

Precision = TP / (TP + FP) over apply-decisions (FP: predicted apply=yes
while the label is no; an extra reject reason on a true rejection is NOT a
false positive — the apply decision is still correct).
Recall   = TP / (TP + FN) over positive labels (FN: predicted rejected while
the label is yes).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from jobharness.parse.normalizers import normalize_compensation
from jobharness.route.router import route_job
from jobharness.schemas.archetype import Archetype
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import Positioning
from jobharness.schemas.profile import Profile
from jobharness.settings import Settings


@dataclass(slots=True)
class GoldenResult:
    job_id: str
    label_apply: bool
    predicted_apply: bool
    label_archetype: str | None
    predicted_archetype: str | None
    label_reject_reasons: list[str]
    predicted_reject_reasons: list[str]
    predicted_score: float | None
    tp: bool = False
    fp: bool = False
    fn: bool = False
    tn: bool = False


@dataclass(slots=True)
class RouterMetrics:
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    archetype_accuracy: float
    wrong_archetype: list[str] = field(default_factory=list)
    results: list[GoldenResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "archetype_accuracy": round(self.archetype_accuracy, 4),
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "wrong_archetype": self.wrong_archetype,
        }


def evaluate_router(
    golden_dir: str | Path,
    profile: Profile,
    positioning: Positioning,
    archetypes: dict[str, Archetype],
    settings: Settings,
) -> RouterMetrics:
    golden_dir = Path(golden_dir)
    results: list[GoldenResult] = []
    archetype_wrong: list[str] = []

    for path in sorted(golden_dir.glob("*.json")):
        if path.stem in ("expected_downgrades", "baseline"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        label: dict[str, object] = data["expected_jd_parsed"]
        # Keep compensation (needed by the compensation filter and scoring);
        # null means "absent" and JDParsed defaults handle it.
        parsed = JDParsed.model_validate(label)

        norm = None
        if parsed.compensation is not None:
            try:
                norm = normalize_compensation(
                    parsed.compensation,
                    settings,
                    hours_per_week=parsed.hours_per_week,
                )
            except Exception:
                norm = None
        result = route_job(
            parsed, profile, positioning, archetypes, settings, normalized_comp=norm
        )
        label_apply = data["expected_apply"] == "yes"
        label_arch = data.get("expected_archetype")
        label_reasons = data.get("expected_reject_reasons", [])
        pred_reasons = result.reject_reasons

        gr = GoldenResult(
            job_id=data["id"],
            label_apply=label_apply,
            predicted_apply=not result.rejected,
            label_archetype=label_arch,
            predicted_archetype=result.archetype,
            label_reject_reasons=label_reasons,
            predicted_reject_reasons=pred_reasons,
            predicted_score=result.score,
        )
        if label_apply and not result.rejected:
            gr.tp = True
        elif label_apply and result.rejected:
            gr.fn = True
        elif not label_apply and result.rejected:
            gr.tn = True
        else:
            gr.fp = True
        if label_apply and label_arch and result.archetype != label_arch:
            archetype_wrong.append(data["id"])
        results.append(gr)

    tp = sum(1 for r in results if r.tp)
    fp = sum(1 for r in results if r.fp)
    fn = sum(1 for r in results if r.fn)
    tn = sum(1 for r in results if r.tn)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    labeled_yes = [r for r in results if r.label_apply and r.label_archetype]
    arch_ok = sum(1 for r in labeled_yes if r.predicted_archetype == r.label_archetype)
    arch_acc = arch_ok / len(labeled_yes) if labeled_yes else 0.0

    return RouterMetrics(
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=precision,
        recall=recall,
        archetype_accuracy=arch_acc,
        wrong_archetype=archetype_wrong,
        results=results,
    )


__all__ = ["GoldenResult", "RouterMetrics", "evaluate_router"]
