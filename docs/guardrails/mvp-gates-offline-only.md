---
id: mvp-gates-offline-only
title: "MVP acceptance steps must run offline with FakeProvider"
status: active
date: 2026-10-08
tags: [testing, llm]
governed-by: "0013"
grounded-in: ["facts/0013"]
derivation-note: >
  Given decision 0013 (MVP is proven offline on fixtures) and fact 0013
  (no real model ids are pinned), no MVP test or acceptance command may
  need a live LLM key or network access.
go-getter:
  enforcement:
    - tier: 1
      check: Run MVP acceptance commands with ANTHROPIC_API_KEY unset and the provider set to fake; a step that needs a live call is out of MVP scope
---

## Guardrail

Tests and acceptance checks for M1–M6 MUST pass with `FakeProvider` fixtures and no network access. A step needing a live provider call, real model ids or a real mailbox belongs after the MVP gate.
