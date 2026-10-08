---
id: "0014"
title: "MVP is a single-user Telegram bot that finds jobs and delivers documents"
status: active
date: 2026-10-08
tags: [planning, safety]
track: product
accepted-by: kaiden
governed-facts: ["0014"]
fitness-functions: ["offline end-to-end test: onboarding, providers, feed, run, deliveries in a fake chat", "owner-only check rejects every other Telegram user id"]
---

## Context

The Principal needs to use the harness without touching config files: open Telegram, fill in a profile, connect providers, add an RSS feed, start the search, and receive a tailored resume, cover letter and job link in chat. This replaces 0013 (MVP as spec milestones M1–M6 with email send and inbox tracking).

## Decision

MVP is reached when this flow works end to end:

- **Single user.** The bot answers only the configured owner's Telegram user id; the existing single-Principal DB and profile model stay.
- **Telegram only.** Profile wizard, provider setup, feed management, start/pause/status and delivery all happen in chat. A website is post-MVP.
- **Keys pasted in chat.** OpenRouter and SuperJob keys are entered in chat, the message is deleted, and the key is stored encrypted (see guardrail `provider-keys-never-persisted-in-clear`). The Telegram bot token and the encryption master key come from the host environment.
- **Profile from the wizard only.** No resume import. Every resume fact comes from what the Principal typed (spec §2.1).
- **Sources.** SuperJob API (queried from the profile) plus RSS feeds the Principal adds. With We Work Remotely via generic RSS this stays within 0007's 1–2 API adapters.
- **Delivery is to the Principal, not to employers.** Resume PDF, cover letter and job link arrive in chat. Nothing is sent to an employer, so spec §2.3 (human approval before sending) is met by construction. Email sending, inbox tracking and follow-ups (old M6) are deferred.
- **Proof.** Automated checks run offline with fakes (guardrail `mvp-gates-offline-only`); a final human live smoke test with real keys closes the MVP.

## Tradeoffs

- Keys in chat match the requested flow but cross Telegram's servers (fact 0014); env-only keys would be safer but need host edits.
- Single-user keeps the spec's data model; multi-user would need per-user tenancy in every table.

Plan: `docs/plans/mvp.md`.
