---
id: docs-manifest
title: "Docs manifest: doc sections mapped to content and watch paths"
status: active
date: 2026-10-08
tags: [docs]
kind: derived
governed-by: "0006"
bootstrap-generated: true
---

# Docs manifest

Maps each human-facing doc section to what it describes and the paths whose change would make it drift. `last-verified` is filled in by `capture`.

| Doc | Section | Describes | Watch paths | last-verified |
|---|---|---|---|---|
| README.md | Quickstart | Telegram setup flow; decisions 0012, 0014, 0015 | src/jobharness/cli.py, src/jobharness/bot/, Dockerfile, .env.example | |
| README.md | Telegram commands | Chat command list | src/jobharness/bot/ | |
| README.md | Architecture | Pipeline modules and ingest adapters | src/jobharness/, config/archetypes/ | |
| README.md | CLI reference | `jh` command groups (spec §14) | src/jobharness/cli.py | |
| README.md | Safety constraints | Spec §2 invariants; fact 0002 | spec.md, src/jobharness/route/filters.py, config/config.example.yaml | |
| README.md | Out of scope | Fact 0002 | spec.md | |
| README.md | Repository layout | Top-level tree | src/jobharness/, tests/, eval_data/, config/ | |
| README.md | Implementation status | Plan status; decision 0001 | docs/plans/changeset-implementation-plan.md | |
| docs/DECISIONS.md | all (frozen legacy log) | Decisions 0001–0009, 0011, 0012; facts 0001, 0003–0009 | docs/decisions/, docs/facts/ | |
| docs/SOURCES.md | Adapter table and sub-rows | Fact 0010; decision 0007 | src/jobharness/ingest/, config/config.example.yaml | |
| docs/SOURCES.md | Rules | Spec §11.1, §2.4 adapter rules | src/jobharness/ingest/base.py, src/jobharness/ingest/dedup.py | |
| docs/PROMPTS.md | Versioning rules and catalogue | Prompt immutability, schemas, eval coverage | src/jobharness/llm/, src/jobharness/llm/prompts/ | |
| docs/PROMPTS.md | Roles → model mapping | Decision 0008; fact 0011 | config/config.example.yaml, src/jobharness/settings.py | |
| docs/PROMPTS.md | FakeProvider | Offline test provider | src/jobharness/llm/fake_provider.py, tests/fixtures/llm/ | |
| docs/RUNBOOK.md | Daily / Weekly / When something is off | Chat workflow (decision 0014) | src/jobharness/bot/ | |
| docs/RUNBOOK.md | Safety reminders | Spec §2 | spec.md | |
| docs/plans/changeset-implementation-plan.md | M1–M8 steps, sign-off list, matrix | Decisions 0001, 0004, 0005 | spec.md, src/jobharness/ | |
| docs/plans/mvp.md | all steps | MVP plan; decisions 0012, 0014, 0015; guardrails mvp-gates-offline-only, provider-keys-never-persisted-in-clear | spec.md, docs/decisions/0014-mvp-is-single-user-telegram-pipeline.md, src/jobharness/ | |
| spec.md | all | Source of record for the project | spec.md | |
