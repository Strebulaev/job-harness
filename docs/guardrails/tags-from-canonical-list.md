---
template-version: 1
seeded: true
id: tags-from-canonical-list
title: Any artifact's tags must come from the canonical tag list, when one exists
status: active
date: 2026-10-08
tags: [knowledge-management, guardrail]
governed-by: TBD
grounded-in: TBD
derivation-note: >
  Seeded from go-getter's shipped guardrail templates; if kept, draft a
  decision recording why, so this isn't permanent debt.
---

## Guardrail

When `docs/skills/tags.md` exists, any fact, decision, guardrail, or
procedure file's `tags` MUST all be entries from that list — whether the
file was written by `bootstrap`/`capture`/`roadmap` or by hand. A tag
found that isn't on the list MUST be flagged as debt: either the list is
missing a genuinely new tag (propose adding it, with a one-line meaning)
or the file should use an existing tag instead of a near-duplicate.

## Derivation

TBD — seeded as a starting point; fill in the descriptive/axiomatic
basis once someone decides why this project keeps it.

## Note

This file was seeded from a go-getter template and is kept in sync
(updated or removed) as that template changes. To adopt it permanently
in its current form and stop future sync from touching it, delete its
`seeded` and `template-version` frontmatter fields.
