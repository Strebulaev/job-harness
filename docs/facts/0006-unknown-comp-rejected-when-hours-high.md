---
id: "0006"
title: "Unknown compensation with high hours is rejected, not asked"
status: active
date: 2026-10-08
tags: [routing]
kind: decision
governed-by: TBD
---

If compensation is unknown and mean `hours_per_week` ≥ `allow_below_floor_if_hours_leq`, the filter rejects with `comp_below_floor` instead of flagging `ask_rate` (golden job g13).
