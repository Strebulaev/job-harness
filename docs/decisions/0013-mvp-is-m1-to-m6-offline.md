---
id: "0013"
title: "MVP is M1–M6 accepted, proven offline on fixtures"
status: active
date: 2026-10-08
tags: [planning, eval]
track: product
accepted-by: kaiden
governed-facts: ["0013"]
fitness-functions: ["pytest tests/e2e passes with FakeProvider and a local fake SMTP/IMAP", "jh eval run --suite all exits zero against stored baselines"]
---

## Context

The spec (§20, §22) defines milestones M1–M8 but no MVP. M1–M3 (ingest, parse, route) are done; M4–M8 are not. The Principal wants the project at MVP, not at full definition of done.

## Decision

MVP is reached when M1–M6 meet their §20 acceptance criteria. That is the first full loop: ingest → parse → route → compose → render → gate → approve → send → track replies. M7 (capacity, reports) and M8 (HTMX UI, Docker, backup) are post-MVP.

Proof is offline:

- Every MVP acceptance run uses `FakeProvider` fixtures, the example profile (`config/profile.example.yaml` content) and test fixtures.
- The M6 E2E test runs against a local fake SMTP/IMAP server.
- PDFs are rendered with the Typst binary (0012).

Post-MVP, outside the gate: replacing the example profile with the Principal's real facts, pinning real model ids and recording live baselines (0008), and one live-mailbox smoke test.

## Tradeoffs

- Offline proof keeps CI free of keys, spend and flakiness, but a live-LLM or live-mail defect can survive until the post-MVP steps.
- Pinning model ids late keeps the irreversible choice (0008) open longer, but prompt v1 baselines recorded against fixtures must be re-recorded against the real models.

Plan: `docs/plans/mvp-m4-m6.md`.
