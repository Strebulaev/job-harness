# jobharness — Decision Log

One-paragraph entries. Each records a genuine choice (with rationale), a descriptive fact (what is true now), or an open decision (needs Principal sign-off). New entries append to the bottom; do not renumber or reorder.

**Frozen legacy log.** Since 2026-10-08 (decision 0010 supersedes D2), new decisions and facts live in `docs/decisions/` and `docs/facts/`; D1–D9 are stubbed there as 0001–0009 and point back here for full text.

**Track:** every entry here is product-track (the harness is a single-user product; build-related choices are decisions about *what* the harness is, not how the team ships).

**Legend:**
- `[DECISION]` — axiomatic; the team commits to this, with context/rationale.
- `[FACT]` — descriptive; what is true now (environmental fact, a value the team chose, a spec constant).
- `[OPEN]` — needs Principal sign-off before the implementing agent proceeds; auto-resolved to the simplest option as a *placeholder* and flagged for override.

---

## Decisions (axiomatic)

### D1 — Changeset plan is milestone-ordered M1→M8, each step self-sufficient
**Track:** product · **Status:** active · **Accepted-by:** Principal · **Date:** 2026-10-03
The changeset implementation plan for the spec is organized by the spec's eight milestones (M1→M8, §20). Each step is self-sufficient for a *cold* agent: it names the exact file paths to create or edit, what to do, why it matters, and what "done" looks like. No step refers to "as discussed above" or to another step's context. Status markers (done / pending / blocked) are maintained in place as work progresses. **Rationale:** the spec §0 mandates "implement milestones in order; do not start N+1 until all acceptance criteria of N pass in CI." A milestone-ordered plan matches that rule; a flat list or a dependency-driven plan would obscure the CI-gate boundary between milestones.

### D2 — Knowledge artifacts follow the spec's existing `docs/` convention
**Track:** product · **Status:** superseded by 0010 (2026-10-08) · **Accepted-by:** Principal · **Date:** 2026-10-03
Durable knowledge lives in the paths the spec already mandates: `docs/DECISIONS.md` (decision log — this file), `docs/SOURCES.md` (per-adapter ToS notes, §19), `docs/PROMPTS.md` (prompt catalogue + versioning rules, §19), `docs/RUNBOOK.md` (Principal's daily/weekly workflow, §19), and the top-level `README.md` (§19). No new NNNN-slug directory tree (`docs/facts/`, `docs/guardrails/`, etc.) is invented. **Rationale:** the spec is self-contained about where knowledge goes; inventing a parallel convention would split the source of truth and force every future reader to learn two layouts.

### D3 — Open items resolve to the simplest option; a visible flag list is maintained
**Track:** product · **Status:** active · **Accepted-by:** Principal · **Date:** 2026-10-03
For every ambiguity in the spec (and the one self-contradiction, D7), the changeset plan picks the simplest option that satisfies the acceptance criteria, records it here as a one-paragraph entry, and lists it in a visible "Open decisions" section of the plan so a cold agent sees the choice and can override before proceeding. **Rationale:** the spec §0 says "when the spec is ambiguous, choose the simplest option that satisfies the acceptance criteria, document the decision in docs/DECISIONS.md, and continue. Do not stall for clarification unless a decision is irreversible or touches section 2." A visible flag list adds the visibility the spec's "document and continue" rule leaves to convention.

### D4 — Dependency matrix is module-level, not milestone-level
**Track:** product · **Status:** active · **Accepted-by:** Principal · **Date:** 2026-10-03
The plan's dependency matrix has one row per pipeline module (foundation + 10 modules from §11: ingest, parse, route, compose, render, eval, send, track, capacity, report) and one column per prerequisite. It is *not* a coarse milestone-level matrix. **Rationale:** a cold agent needs to know "which module's code must exist before I can write this module's tests," not just "which milestone comes next." Module-level fits the spec's own structure (§11.1–§11.10) and is the natural unit of code organization.

### D5 — Golden sets are authored in-plan, mapped to their consuming milestones
**Track:** product · **Status:** active · **Accepted-by:** Principal · **Date:** 2026-10-03
The three golden sets the spec mandates (§4, §13.3) — `eval_data/golden_jobs/` (≥30 JDs), `eval_data/golden_claims/` (≥60 snippets), `eval_data/golden_emails/` (≥50 labeled emails) — are *authored* as explicit plan steps, not assumed pre-existing. Authoring steps are placed in the milestones that consume them: jobs → M2/M3, claims → M5, emails → M6. **Rationale:** the eval suites (§13.3) are the regression gates that "any change to prompts, models, or router weights MUST include an eval run artifact in the PR." A cold agent that assumes the fixtures exist will stall at M3/M5/M6 with nothing to test against.

### D6 — Doc completeness bar: spec-mandated sections, verified by content
**Track:** product · **Status:** active · **Accepted-by:** Principal · **Date:** 2026-10-03
Each required doc (README, DECISIONS, SOURCES, PROMPTS, RUNBOOK) is "done" when it contains the specific sections the spec names for it — not merely when the file exists. The plan's per-doc done-when greps for those sections. **Rationale:** the spec §19 names concrete content for each doc (README: quickstart + architecture + CLI + safety; SOURCES: per-adapter ToS entry; PROMPTS: each prompt's intent + coverage; RUNBOOK: morning/midday/weekly). Existence-only checking would let a file pass that is an empty shell, defeating the doc's purpose for the next Principal or agent.

### D7 — Spec self-contradiction on adapter count: resolve to the smaller (1–2 API adapters)
**Track:** product · **Status:** active · **Accepted-by:** Principal · **Date:** 2026-10-03 · **Flag:** IRREVERSIBLE — requires Principal sign-off
§11.1 says "2–3 API/RSS-based adapters from the list in docs/SOURCES.md." §20 M2 says "+ 1–2 permitted API adapters." These conflict. **Resolution:** the smaller (1–2 API adapters) wins, matching §20 M2 (the acceptance-criteria milestone, which is the operative constraint). **Rationale:** the spec §0 says "when the spec is ambiguous, choose the simplest option that satisfies the acceptance criteria." M2's acceptance criterion is the one that gates the next milestone; the smaller number also reduces the ToS surface (§2.4) and the number of adapters that must be kept current. This is flagged as irreversible in the plan's "needs Principal sign-off" section because picking the wrong number now means re-doing M2's adapter work and re-baselining the M3 router precision/recall against a different fixture set.

### D8 — LLM provider/model choice is flagged IRREVERSIBLE
**Track:** product · **Status:** active · **Accepted-by:** Principal · **Date:** 2026-10-03 · **Flag:** IRREVERSIBLE — requires Principal sign-off
The default provider in §12 is "Anthropic API via the official SDK; model ids come from config, never hard-coded." The spec allows `provider: anthropic | fake` (§5). **Decision:** the provider choice and the concrete model ids (parse / compose / judge / classify roles) are flagged as irreversible in the plan — they must be confirmed by the Principal before M1. **Rationale:** once prompt versions are released and the golden-set baselines are recorded against a specific model+prompt-version pair (§13.3: "CI fails if precision drops > 3 points vs. the stored baseline"), swapping the provider or model re-baselines every golden set and every judge score. The spec already mitigates this with `prompt_version` + `model` stored on every `documents` row and `llm_calls` row (§6, §12), but the *initial* choice is the one that anchors the baseline.

### D9 — All decision artifacts are product-track
**Track:** product · **Status:** active · **Accepted-by:** Principal · **Date:** 2026-10-03
No decision in this spec is process-track. Even build-related choices (adapter count D7, provider choice D8) are product-track: they decide *what the harness is* (which sources it touches, which LLM it talks to), not *how the team ships*. **Rationale:** the spec is a single-user product for one Principal; there is no team, no org process, no CI-to-production pipeline that a process-track decision would govern. Forcing a product/process split would put every entry in the wrong bucket.

---

## Descriptive facts

These are not choices — they are constants the spec fixes or values the team has already committed to. They are recorded here so a cold agent does not re-derive them.

- **F1 — Golden set sizes.** `eval_data/golden_jobs` ≥ 30 JDs; `eval_data/golden_claims` ≥ 60 resume snippets with fact sets and expected labels; `eval_data/golden_emails` ≥ 50 labeled inbound emails. Sources: §4 (layout), §13.3 (regression metrics). Recall on fabrications ≥ 0.95; router precision/recall ≥ 0.85/0.80; email classifier macro-F1 ≥ 0.85.
- **F2 — Out-of-scope list (§21).** The system MUST NOT build: (a) automated submission to platforms that forbid automation; (b) CAPTCHA solving; (c) account farming; (d) scraping that violates ToS; (e) generation/storage/sending of false credentials, references, or identity claims; (f) features that conceal the Principal's identity after engagement begins or let someone other than the contracted party perform contracted work without written client consent; (g) automatic acceptance of offers or signing of contracts; (h) LinkedIn automation bots.
- **F3 — Required docs.** `README.md`, `docs/DECISIONS.md` (this file), `docs/SOURCES.md`, `docs/PROMPTS.md`, `docs/RUNBOOK.md`. Sources: §19 (Documentation deliverables) plus the explicit instruction to add RUNBOOK.
- **F4 — Spec self-contradiction.** §11.1 "2–3 API/RSS-based adapters" vs §20 M2 "1–2 permitted API adapters." Resolved to 1–2 per D7.
- **F5 — Two irreversible items.** Adapter count (D7) and LLM provider/model choice (D8) are the only two items in this spec that block the implementing agent until the Principal signs off. Everything else auto-resolves to the simplest option per D3.

---

## Open decisions (needs Principal sign-off before the implementing agent proceeds)

> These are *not* dropped — they are resolved-to-simplest as a placeholder (per D3) and listed here so a cold agent sees the choice and can override. The plan's "Needs Principal sign-off" section cross-references each of these.

- **O1 — Adapter count (D7).** **Signed off: 1–2** (Principal, 2026-10-04). M2-2 implements 1 API/RSS adapter (We Work Remotely via the generic RSS adapter). *Irreversible once M3's baseline is recorded.*
- **O2 — LLM provider + model ids (D8).** **Baseline recorded** (2026-10-05). Placeholder: Anthropic, with `llm.models.parse/compose/judge/classify` set in `config/config.yaml` to the Principal's chosen model ids. Override by changing `llm.provider` and re-running all golden sets. *Irreversible once prompt versions v1 are released and baselines recorded.*
- **O3 — `fx_as_of` date for static FX table (§10).** The spec says "MAY be refreshed manually." Placeholder: set once in M1, then manual refresh is a runbook task, not a CI step. Not irreversible, but a cold agent should not pick a date silently.
- **O4 — Typst vs Pandoc/WeasyPrint for PDF rendering (§3).** Spec says "Jinja2 + Typst (preferred) or Pandoc/WeasyPrint." Placeholder: Typst. Override before M4 (render) starts; the `typst_renderer.py` module and the G5 "PDF text extractable" gate are typed to the renderer.

## Facts / decisions recorded during M3 (2026-10-05)

- **Router hard filters collect all reasons.** The 8 hard filters (engagement_type, exclusivity, onsite_required, country allow/deny, overlap, compensation, ai_tools_policy, red-flag blocklist) all run and accumulate reasons/flags; no short-circuit on first rejection. This matches the spec §11.3 "any failure -> rejected, reasons stored" (plural).
- **Overlap filter runs even for onsite jobs.** The overlap check is not skipped when `remote_policy == "onsite"` or `onsite_required == True`. Both filters fire independently so all applicable reasons are recorded.
- **Compensation filter treats unknown comp as below-floor when hours exceed exception threshold.** If `compensation` is null/unknown and `hours_per_week` mean >= `allow_below_floor_if_hours_leq`, the filter rejects with `comp_below_floor` rather than flagging `ask_rate`. This matches the golden job g13 expectation.
- **Archetype selection uses whole-word matching for must_have keywords.** The scoring matches must_have_keywords against required terms (exact) or whole-word in the archetype text (using regex word boundaries). This prevents false positives like "api" matching "fastapi" or "sql" matching "postgresql".
- **Router golden baseline recorded.** Baseline at precision=1.0, recall=0.933, archetype_accuracy=0.867 stored in `eval_data/golden_jobs/baseline.json`. CI step `jh eval run --suite router` compares current precision to baseline and fails if dropped > 3 points.
- **`eval` CLI command added.** `jh eval run --suite router` runs the router golden evaluation and compares to baseline.
- **`eval_data/golden_jobs/baseline.json` excluded from golden job processing.** All golden job loaders (validator, parser tests, router tests) now skip `baseline.json` alongside `expected_downgrades.json`.

---
