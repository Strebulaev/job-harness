---
id: "0012"
title: "CI enforces ruff, mypy strict, pytest, init/validate, router baseline"
status: active
date: 2026-10-08
tags: [ci, testing]
kind: environmental
governed-by: TBD
---

`.github/workflows/ci.yml` runs `ruff check src/ tests/`, `mypy` (strict), `pytest tests/unit tests/integration`, `jh init` + `jh profile validate --path config/profile.example.yaml`, and `jh eval run --suite router --json`.
