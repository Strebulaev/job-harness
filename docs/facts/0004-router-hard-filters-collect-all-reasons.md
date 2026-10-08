---
id: "0004"
title: "Router hard filters all run and accumulate reasons"
status: active
date: 2026-10-08
tags: [routing]
kind: decision
governed-by: TBD
---

The 8 hard filters (engagement_type, exclusivity, onsite_required, country allow/deny, overlap, compensation, ai_tools_policy, red-flag blocklist) never short-circuit; all reasons and flags are stored (spec §11.3).
