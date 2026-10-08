---
id: "0010"
title: "Adopt the typed docs/{facts,decisions,guardrails,skills} tree, superseding D2"
status: active
date: 2026-10-08
tags: [docs, knowledge-management]
track: product
accepted-by: kaiden
---

## Context

D2 (0002) ruled out a typed knowledge tree. The Principal chose to supersede it during a `bootstrap` run so facts, guardrails and procedures can be tracked with provenance and drift checks.

## Decision

Knowledge artifacts live in `docs/{facts,decisions,guardrails,skills}/`. D1–D9 from `docs/DECISIONS.md` are stubbed as 0001–0009 and point back to the full text; `docs/DECISIONS.md` is frozen as the legacy log and new decisions go in `docs/decisions/`. The spec-mandated docs (README, SOURCES, PROMPTS, RUNBOOK, DECISIONS) stay as they are.

<!-- looks like a decision, could be a behavioral rule — classify before finalizing: knowledge layout is process-like, but D9 (0009) says no decision is process-track -->
