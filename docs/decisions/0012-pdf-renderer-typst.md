---
id: "0012"
title: "PDF renderer is the Typst binary on PATH"
status: active
date: 2026-10-08
tags: [render]
track: product
accepted-by: kaiden
---

## Context

Spec §3 prefers Typst, allows Pandoc/WeasyPrint. `typst_renderer.py` and the G5 "PDF text extractable" gate are typed to the renderer.

## Decision

Use the `typst` binary on PATH, not the PyPI package, Pandoc or WeasyPrint. Signed off 2026-10-08. `typst` is installed in CI only, not on the dev machine; render tests skip locally. CI wiring is plan step 0.1 in `docs/plans/mvp-m4-m6.md`.

Full text: `docs/DECISIONS.md` O4.
