---
id: mvp-gates-offline-only
title: "Automated MVP checks must run offline with fakes"
status: active
date: 2026-10-08
tags: [testing, llm]
governed-by: "0014"
grounded-in: ["facts/0013"]
derivation-note: >
  Given decision 0014 (MVP is proven by offline automated checks plus one human live smoke test) and fact 0013
  (no real model ids are pinned), no MVP test or acceptance command may
  need a live LLM key or network access.
go-getter:
  enforcement:
    - tier: 1
      check: Run automated checks with no provider keys in the environment and the provider set to fake; a check needing a live call belongs in the human smoke test
---

## Guardrail

Automated tests and acceptance commands MUST pass with `FakeProvider`, mocked HTTP (SuperJob, OpenRouter, RSS) and a fake Telegram messenger, with no network access. Live calls with real keys happen only in the human smoke test (plan step 6.3).
