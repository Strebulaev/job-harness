---
id: "0012"
title: "CI enforces ruff, mypy strict, pytest, init/validate, router baseline"
status: active
date: 2026-10-08
tags: [ci, testing]
kind: environmental
governed-by: TBD
---

`.github/workflows/ci.yml` runs `ruff check src/ tests/`, `mypy` (strict), `pytest tests/unit tests/integration`, `jh init` + `jh profile validate --path config/profile.example.yaml`, `jh eval run --suite all --json` (router + golden claims), pinned Typst 0.13.1 install, `pytest tests/e2e`, and a Docker image build.
