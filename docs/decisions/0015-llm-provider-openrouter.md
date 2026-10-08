---
id: "0015"
title: "LLM provider is OpenRouter, with models chosen by the Principal in chat"
status: active
date: 2026-10-08
tags: [llm]
track: product
accepted-by: kaiden
---

## Context

0008 fixed Anthropic as an irreversible provider choice. The Principal wants to connect OpenRouter instead, so one key reaches many models.

## Decision

Add an `openrouter` provider (OpenAI-compatible chat completions) and make it the MVP default. Model ids for the parse, compose, judge and classify roles are picked by the Principal in `/models` and stored in user settings. Structured outputs use `response_format` with a strict JSON schema and `require_parameters`, because support varies per model and provider. The Anthropic and fake providers remain. Prompt-version baselines recorded against fixtures must be re-recorded against the chosen models.

Supersedes 0008.
