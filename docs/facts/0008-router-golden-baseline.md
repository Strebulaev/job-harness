---
id: "0008"
title: "Router golden baseline: P=1.0, R=0.933, archetype acc=0.867"
status: active
date: 2026-10-08
tags: [routing, eval]
kind: environmental
governed-by: "0005"
---

Measured 2026-10-08 by `jh eval run --suite router` (14 TP, 0 FP, 1 FN); `eval_data/golden_jobs/baseline.json` was refreshed to these values (it held an older recall of 0.833). CI (`jh eval run --suite router`) fails if precision drops >3 points.
