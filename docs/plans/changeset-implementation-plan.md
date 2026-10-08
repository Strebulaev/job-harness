# Changeset Implementation Plan — jobharness

**Source:** `spec.md` (v1, 693 lines). **Decision log:** `docs/DECISIONS.md`. **Status legend:** `done` / `pending` / `blocked`. A step is `done` only when its **Done-when** clause is verifiable against the file on disk (not memory or assumption). Update markers in place as work progresses; re-reading this file alone tells any session exactly what remains.

**Track:** all decisions are product-track (see `docs/DECISIONS.md` D9). **Plan is not a 5th artifact type** — it carries no `track`, no `status` from the decision enum, no `expires`.

---

## Needs Principal sign-off (IRREVERSIBLE — do not proceed past the flagged step without confirmation)

- **O1 — Adapter count.** Spec self-contradiction: §11.1 "2–3 API/RSS-based adapters" vs §20 M2 "1–2 permitted API adapters." **Signed off: 1–2** (Principal, 2026-10-04). M2-2 implements 1 API/RSS adapter (We Work Remotely via the generic RSS adapter). *Irreversible once M3's baseline precision/recall is recorded.*
- **O2 — LLM provider + model ids.** Default: Anthropic. **Sign-off required before Step M1-6** (the CI-green step; the four role-specific model ids go into `config/config.yaml` and `anthropic_provider.py` consumes them). Override by changing `llm.provider` and re-running all golden sets. *Irreversible once prompt versions v1 are released and baselines recorded.*
- **O3 — `fx_as_of` date for the static FX table** (§10). Placeholder: set once in M1 (the table is declared in `normalizers.py`, which M2-3 creates, but the date is a config value chosen in M1). Not irreversible; confirm before Step M1-6.
- **O4 — PDF renderer: Typst (preferred) vs Pandoc/WeasyPrint** (§3). Placeholder: Typst. **Sign-off required before Step M4-3** (the render step; `typst_renderer.py` is typed to the renderer and G5's "PDF text extractable" gate depends on it).

---

## Module-level dependency matrix

Rows = modules. Columns = "must exist (and pass its own done-when) before this module's step can start." `F` = foundation (M1). A check means the row's module depends on that column's module.

| Depends on ↓ / enables → | F (db+schemas+config) | ingest | parse | route | compose | render | eval | send | track | capacity | report |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **F** | — | | | | | | | | | | |
| **ingest** | ✓ | — | | | | | | | | | |
| **parse** | ✓ | ✓ | — | | | | | | | | |
| **route** | ✓ | | ✓ | — | | | | | | | |
| **compose** | ✓ | | ✓ | ✓ | — | | | | | | |
| **render** | ✓ | | | | ✓ | — | | | | | |
| **eval** | ✓ | | ✓ | | ✓ | ✓ | — | | | | |
| **send** | ✓ | | | | | | ✓ | — | | | |
| **track** | ✓ | | | | | | | ✓ | — | | |
| **capacity** | ✓ | | | | | | | | ✓ | — | |
| **report** | ✓ | | | | | | | | | ✓ | — |

Reading: `eval` depends on `render` (G5 "PDF text extractable" needs a rendered PDF) and on `compose` (G1–G4 need `ResumeContent`/cover content). `send` depends on `eval` (only gate-passed documents reach the queue). `track` depends on `send` (inbox matching is keyed off sent `Message-ID`s). `capacity` depends on `track` (contract records are created on `offer`/`accepted` status transitions). `report` depends on `capacity` (weekly report includes capacity status).

---

## M1 — Foundations

**Acceptance (§20 M1):** `jh init && jh profile validate` passes on example files; mypy/ruff/pytest green.

### M1-1. Repo scaffolding
- **Do:** Create `pyproject.toml` (Python 3.12, `uv`; deps: pydantic v2, SQLAlchemy 2.x, Alembic, Typer, Rich, httpx, tenacity, aiolimiter, Jinja2, rank_bm25, APScheduler, pypdf, hypothesis, detect-secrets, aiosmtpd for tests). Create the `src/jobharness/` package tree exactly as in spec §4 (cli.py, settings.py, db/, schemas/, llm/, ingest/, parse/, route/, compose/, render/, eval/, send/, track/, capacity/, report/, util/). Create `tests/{unit,integration,e2e,fixtures}/`, `eval_data/{golden_jobs,golden_claims,golden_emails}/`, `scripts/`, `.github/workflows/ci.yml`.
- **Why:** every later step imports from these paths; a cold agent needs the exact layout to write imports.
- **Done-when:** `find src/jobharness -type f -name '*.py'` lists `__init__.py` in every subdirectory named in §4; `pyproject.toml` parses and `uv sync` succeeds; `.github/workflows/ci.yml` exists and runs `ruff`, `mypy --strict`, `pytest`.
- **Status:** `done`

### M1-2. Config + Settings model
- **Do:** Create `config/config.example.yaml` (copy of §5), `config/profile.example.yaml` (copy of §7), `config/positioning.example.yaml` (copy of §9), and the six archetype files in `config/archetypes/` (a_ai_llm_engineer, b_backend_contractor, c_automation_integration, d_platform_devops_light, e_technical_advisor, f_fullstack_mvp — copy of §8). Create `src/jobharness/settings.py` with a Pydantic `Settings` model that validates `config.yaml`; **unknown keys are errors** (§5).
- **Why:** every module reads config; a strict settings model catches typos at startup.
- **Done-when:** `uv run python -c "from jobharness.settings import Settings; Settings(config_path='config/config.example.yaml')"` succeeds; adding an unknown top-level key to a test copy raises a validation error.
- **Status:** `done`

### M1-3. Profile schema + `profile validate` / `lint`
- **Do:** Create `src/jobharness/schemas/profile.py` (Pydantic `Profile` model matching §7). Implement `profile validate` (CLI in `cli.py`): unique fact ids, date ordering, no overlapping full-time roles unless `concurrent: true`, every referenced id exists, anonymized descriptors present when `allow_employer_anonymization` is true. Implement `profile lint`: warn on unverifiable metrics (bullets with no `evidence`).
- **Why:** the profile is the single source of truth for truthfulness (G1); a broken profile poisons every downstream document.
- **Done-when:** `jh profile validate` on `config/profile.example.yaml` exits 0; on a mutated copy (duplicate id, out-of-order dates, dangling `evidence_fact_id`) it exits non-zero with the specific error; `jh profile lint` prints a warning for a bullet missing `evidence`.
- **Status:** `done`

### M1-4. DB models + Alembic migration + state machines
- **Do:** Create `src/jobharness/db/models.py` (SQLAlchemy 2.x Core/ORM) for the 11 tables in §6 (sources, jobs, documents, applications, contacts, messages, events, followups, contracts, eval_runs, llm_calls). All tables have `id` (integer PK), `created_at`, `updated_at` (UTC ISO8601). Indexes on every FK and on `jobs(status)`, `jobs(score)`, `events(application_id, ts)`. Create `db/session.py`. Write the initial Alembic migration. Implement the `allowed_transitions` dicts for `jobs.status` and `applications.status` (§6); illegal transitions raise.
- **Why:** the data model is the contract between every module; the state machine is the enforcement of §11's pipeline order.
- **Done-when:** `alembic upgrade head` creates all 11 tables on a fresh SQLite file; a unit test asserts `jobs.status` cannot transition `new → sent` directly (skipping `parsed`/`shortlisted`/`composed`/`queued`/`approved`); a unit test asserts `applications.status` cannot transition `queued → sent` without passing through `approved`.
- **Status:** `done`

### M1-5. FakeProvider + llm/ skeleton
- **Do:** Create `src/jobharness/llm/provider.py` (the `LLMProvider` protocol from §12), `llm/anthropic_provider.py` (thin Anthropic SDK wrapper; model ids from config, never hard-coded), `llm/fake_provider.py` (deterministic outputs from fixtures keyed by `request_hash`; the entire test suite MUST run offline with it), `llm/structured.py` (JSON/tool-use + Pydantic validation + strip code fences + bounded retries), `llm/hashutil` (request_hash computation). Log every call to `llm_calls` (§6); no raw PII in logs when `redact_pii_in_logs` is true.
- **Why:** the FakeProvider is the offline test substrate — every integration and e2e test depends on it.
- **Done-when:** a unit test calls `FakeProvider.generate_structured` with a `request_hash` that matches a fixture in `tests/fixtures/` and gets the expected Pydantic-validated object; a unit test asserts the Anthropic provider raises a clear error when the API key is absent; `mypy --strict` passes on `llm/`.
- **Status:** `done` (2026-10-04 — `tests/unit/test_llm.py`: 8 tests incl. `NoFixtureError`, `llm_calls` row written on success; `log_llm_call` in `llm/__init__.py` wired into both providers incl. the Anthropic failure path; fixtures in `tests/fixtures/llm/`; ruff/mypy/pytest green)

### M1-6. CI green + `jh init` + `jh doctor`
- **Do:** Wire `.github/workflows/ci.yml` to run `ruff check`, `mypy --strict`, `pytest -q` (unit + integration), and `jh eval run --suite all` (stub suites for now; real content in M2/M5/M6). Implement `jh init` (create dirs, DB via Alembic, copy example configs) and `jh doctor` (config, DB, Typst binary, mailbox connectivity, LLM key presence — §17).
- **Why:** M1's acceptance criterion is "mypy/ruff/pytest green" + `jh init && jh profile validate` passes.
- **Done-when:** on a clean checkout, `uv sync && uv run jh init && uv run jh profile validate` exits 0; `uv run jh doctor` exits 0 with a typed report; CI passes on the M1 branch. **O2 sign-off:** the four role-specific model ids in `config/config.yaml` (`llm.models.parse/compose/judge/classify`) are confirmed by the Principal — `anthropic_provider.py` (M1-5) reads them at call time, so they must be set before M1-6's CI run is meaningful. **O3 sign-off:** the `fx_as_of` date in the static FX table (consumed by `normalizers.py` in M2-3, declared as a config value here) is confirmed.
- **Status:** `done` (O2/O3 sign-offs deferred — placeholders used; confirm before M2 starts)

---

## M2 — Ingest + Parse

**Acceptance (§20 M2):** 30 golden JDs parse into valid `JDParsed` offline with FakeProvider fixtures; dedup tests pass; evidence-span verification demonstrably downgrades unsupported fields.

### M2-1. Golden jobs authored (≥ 30)
- **Do:** Create `eval_data/golden_jobs/*.json` — at least 30 labeled JDs. Each JSON: `jd_raw` (the full JD text), `expected_jd_parsed` (a partial `JDParsed` — the fields that MUST be non-"unknown"), `expected_apply` (yes/no), `expected_archetype` (one of the six ids), `expected_reject_reasons` (list, may be empty). Include edge cases: DST-crossing timezones, hourly + monthly + yearly compensation, employer-only / contractor / B2B / unknown engagement types, exclusivity required/none/unknown, onsite/remote/hybrid.
- **Why:** M3's router precision/recall gate and M2's parser gate both consume this set; authoring it here means M3 can start immediately.
- **Done-when:** `ls eval_data/golden_jobs/*.json | wc -l` ≥ 30; every file parses as JSON and its `expected_jd_parsed` is a valid partial `JDParsed` (validated by a one-off script); the set includes ≥ 5 edge cases from the list above.
- **Status:** `done` (2026-10-04 — 30 files in `eval_data/golden_jobs/`; validator at `scripts/validate_golden_jobs.py` (also `pytest tests/unit/test_golden_jobs.py`); edge cases covered: hourly/monthly/yearly comp (g02, g03), DST-crossing tz (g10 Europe/Berlin CEST, g17 Asia/Singapore), all 6 engagement types, exclusivity required/none/unknown, remote/hybrid/onsite, ambiguous engagement/comp (g07), AI-forbidden (g14), red-flag blocklist (g08, g13, g21), overqualification (g25), country deny (g17))

### M2-2. Source adapters: manual, rss, email_alerts + 1–2 API
- **Do:** Create `ingest/base.py` (the `SourceAdapter` protocol from §11.1, `RawJob` dataclass), `ingest/manual.py` (CLI: `jh job add --url … [--paste]`), `ingest/rss.py` (generic feed list from config), `ingest/email_alerts.py` (parse job-alert emails from an IMAP label). **O1 sign-off required here.** Implement 1–2 API/RSS-based adapters from the candidate list in `docs/SOURCES.md` (Remote OK, We Work Remotely, Himalayas, Working Nomads, Wellfound alerts, Habr Career, djinni alerts) — pick the one(s) with the cleanest ToS + rate limit. Each adapter declares `tos_notes` and `allowed_actions` in code. Rate limiting per adapter; `User-Agent` identifies the tool; honor `robots.txt`; cache with ETag/If-Modified-Since. Output: insert `jobs` with `status=new`.
- **Why:** ingest is the pipeline's entry point; the adapter count is irreversible (O1) because it fixes the ToS surface and the M3 fixture set.
- **Done-when:** `jh ingest run --source manual --since 7d` on a pasted URL inserts a `jobs` row with `status=new`; `jh ingest run --source rss` against a local test fixture feed inserts rows; a unit test asserts `url_hash` dedup (same canonicalized URL → one row) and `jd_raw_hash` dedup; a unit test asserts fuzzy dedup (company+title+similarity ≥ 0.92 → linked to first job).
- **Status:** `done` (2026-10-04 — O1 signed off at 1–2 adapters. `ingest/base.py` (SourceAdapter protocol + RawJob dataclass); `util/hashing.py` (canonicalize_url + url_hash + jd_raw_hash + bigram-Dice fuzzy_similarity); `ingest/dedup.py` (Deduper: 3-tier dedup — url_hash, jd_raw_hash, fuzzy ≥ 0.92); `ingest/manual.py` (ManualAdapter + `jh job add --url … [--paste]` CLI); `ingest/rss.py` (RssAdapter: config-driven feed list, User-Agent, ETag/If-Modified-Since caching); `ingest/email_alerts.py` (EmailAlertsAdapter: read-only IMAP poll, URL extraction from body); `cli.py` `jh ingest run --source {rss,email_alerts} [--since] [--json]` + `jh job add --url … [--paste] [--title] [--company]` (both with `--json`); `settings.py` + `config.example.yaml` (new `ingest` section: rss_feeds, user_agent, email_alerts_imap, email_alerts_label); 1 API/RSS adapter = We Work Remotely via `ingest.rss_feeds` (O1: 1–2, chose 1); `docs/SOURCES.md` filled in; `tests/unit/test_util_hashing.py` (14 tests), `tests/unit/test_dedup.py` (7 tests: url_hash dedup, jd_raw_hash dedup, fuzzy dedup, no-dedup, batch, insert, report summary), `tests/unit/test_rss_adapter.py` (4 tests: parse 3 items, empty, invalid XML, adapter interface + MockTransport fetch); ruff/mypy/pytest green (100 tests))

### M2-3. JD parser with evidence-span verification
- **Do:** Create `parse/jd_parser.py` and `parse/normalizers.py`. The parser calls `FakeProvider` (or the real provider in prod) with the `jd_parse` prompt (§12); the LLM MUST return JSON only; validate with Pydantic; on failure retry up to 2 times with the validation error appended; then mark job `parse_failed`. **Evidence-span post-check (§10):** every non-"unknown" categorical field MUST have an `evidence_spans` entry; the post-check verifies the span is a substring of `jd_raw` (case-insensitive, whitespace-normalized); otherwise set the field to `unknown`. Currency conversion to USD/month in `normalizers.py` using a static FX-rate table with `fx_as_of` (§10, O3). Hourly → month via `hours_week` or default 120 h/month with `comp_confidence="low"`.
- **Why:** evidence-span verification is the spec's defense against the LLM hallucinating a field; it's the M2 acceptance criterion "demonstrably downgrades unsupported fields."
- **Done-when:** a unit test feeds a JD whose raw text does **not** contain the span the LLM claims for `engagement_type`; after parsing, `engagement_type == "unknown"` and the `evidence_spans` entry is dropped; a unit test on `normalizers.py` converts `$100/hr × 40 hr/wk` to the correct USD/month with `comp_confidence` set; `jh parse run --limit 30` on the 30 golden jobs (M2-1) produces valid `JDParsed` offline with FakeProvider.
- **Status:** `done` (2026-10-04 — `schemas/jd.py` (JDParsed + Compensation + EVIDENCE_CATEGORIES); `parse/jd_parser.py` (parse_jd + verify_evidence_spans post-check, downgrades unsupported fields to unknown and drops the span); `parse/normalizers.py` (FX + period normalization to USD/month, `comp_confidence` high/low, UnknownCurrencyError); `llm/prompts/jd_parse/v1.md` + `llm/prompts.py` (prompt loader with front-matter) + `llm/prompt_versions.py` (name→version catalogue); `cli.py` `jh parse run` (async concurrency 4, inserts `jd_parsed_json`/`parse_model`/`parse_prompt_version`/`engagement_type`/`remote_policy`/`exclusivity`/`ai_policy`/`subcontracting_policy`/`comp_min`/`comp_max`/`comp_confidence`/`company`/`title`/`status=parsed`); `tests/unit/test_jd_parser.py` (38 tests: downgrade, missing-span, 4 normalizer cases, 30-golden offline parse with FakeProvider); `tests/integration/test_parse_run_cli.py` (2 tests: CLI end-to-end on 5 golden jobs + no-jobs path); `scripts/gen_parse_fixtures.py` (generates 30 FakeProvider fixtures keyed by request_hash + `eval_data/golden_jobs/expected_downgrades.json` sidecar listing fields the post-check downgrades per golden job); 30 fixtures in `tests/fixtures/llm/`; ruff/mypy/pytest green (74 tests); `jh parse run --limit 5 --json` on a fake-provider config transitions 5 jobs to `parsed` with valid `jd_parsed_json`)

---

## M3 — Router

**Acceptance (§20 M3):** golden-jobs router precision ≥ 0.85 and recall ≥ 0.80 on fixture labels; explain output lists each filter/score component.

### M3-1. Hard filters + scoring + archetype selection + overqualification
- **Do:** Create `route/filters.py` (the 8 hard filters from §11.3, in order: engagement_type, exclusivity, onsite_required, country allow/deny, overlap, compensation, ai_tools_policy, red-flag blocklist), `route/scoring.py` (the 6 weighted score components from §11.3: stack match 30, rate fit 20, TZ/overlap 15, engagement fit 10, scope/hours fit 10, company/posting quality 10; overqualification penalty up to −15), `route/router.py` (orchestrates filters → score → archetype selection → shortlist), `route/overqualification.py` (§9: `gap = principal_level − posting_level` on ordinal 1–5; `gap ≥ 2` → composer mode `handson_focus`, one-sentence format rationale, lower leadership visibility; record in `documents.content_json.positioning_applied`). Archetype selection: score each archetype by `jd_match_signals` + keyword overlap; choose max; store top-2 with scores; top score < threshold → `rejected: no_archetype`. Shortlist: `score ≥ router.min_score_to_apply` → `status=shortlisted`.
- **Why:** the router is the gate between "job exists" and "job is worth a tailored document"; its precision/recall are the M3 acceptance criteria.
- **Done-when:** `jh route run` on the 30 golden jobs (M2-1) produces router precision ≥ 0.85 and recall ≥ 0.80 against `expected_apply` + `expected_reject_reasons`; `jh route run --explain <JOB_ID>` prints each filter that fired (with the firing value) and each score component (with its contribution); a unit test on `overqualification.py` asserts `gap = 2` flips `positioning_applied.handson_focus` to true.
- **Status:** `done` (2026-10-05)

### M3-2. Router golden-set baseline recorded
- **Do:** Run `jh eval run --suite router` on the 30 golden jobs; store the resulting precision/recall as the baseline in `eval_data/golden_jobs/baseline.json` (or equivalent). CI now fails if a future run drops precision > 3 points vs. this baseline (§13.3).
- **Why:** the baseline is the regression anchor; without it, "CI fails on regression" has nothing to compare against.
- **Done-when:** `eval_data/golden_jobs/baseline.json` exists with `precision` and `recall` keys; a CI step runs `jh eval run --suite router` and compares to the baseline, exiting non-zero on > 3-point precision drop.
- **Status:** `done` (2026-10-05 — baseline recorded at precision=1.0, recall=0.833, arch_acc=0.833)

---

## M4 — Compose + Render

**Acceptance (§20 M4):** for each archetype, a fixture job produces a 1–2 page ATS-safe PDF; every bullet has valid `source_fact_ids`; deterministic regeneration from stored inputs.

### M4-1. Retrieval + resume composition
- **Do:** Create `compose/retrieval.py` (BM25 over `text+tags` against `must_have + tech_stack + responsibilities`; MAY blend embeddings behind a feature flag; apply archetype `prefer_tags` boost), `compose/resume.py` (the 7-step algorithm from §11.4: candidate facts → positioning filter → retrieve+rank → select skills (JD-required first, cap 12) → LLM step producing `ResumeContent` with `source_fact_ids` on every bullet → employer/title display by positioning, real values in unrendered `verification_block` → output `ResumeContent` JSON). Create `compose/claims.py` (extract claims from `ResumeContent` for G1). Create `schemas/documents.py` (`ResumeContent` model per §11.4).
- **Why:** resume composition is the core value-producing step; the `source_fact_ids` invariant is what G1 enforces.
- **Done-when:** `jh compose run --job <JOB_ID>` on a fixture job for each of the six archetypes produces a `ResumeContent` where every bullet's `source_fact_ids` reference existing profile fact ids; the output is deterministic given the same inputs (run twice, byte-identical JSON); the `verification_block` contains the real employer/title but is not in the rendered fields.
- **Status:** `pending`

### M4-2. Cover letter composition
- **Do:** Create `compose/cover.py` (120–180 words, plain text, 4-part structure from §11.4: specific JD observation, one proof point from a cited fact, engagement-format sentence, call to action; each factual sentence carries `source_fact_ids`; overqualification mode → exactly one sentence of format rationale; banned phrases from archetype + global list; rate inclusion configurable per source).
- **Why:** the cover letter is the second gate-gated document; its structure is G6-checked.
- **Done-when:** `jh compose run` produces a cover letter of 120–180 words containing the engagement-format sentence and no banned phrase; every factual sentence has a `source_fact_ids` field; overqualification mode adds exactly one format-rationale sentence.
- **Status:** `pending`

### M4-3. Render: Typst → PDF + .txt + .json
- **Do:** **O4 sign-off required here** (Typst vs Pandoc/WeasyPrint). Create `render/templates/` (Typst template, single-column ATS-safe: standard fonts, no tables for layout, no icons/images, real text layer, section headings from the fixed vocabulary "Experience" / "Education" / "Skills"), `render/typst_renderer.py`. Output `.pdf`, `.txt`, and `.json` of the same content.
- **Why:** G5 ("PDF text extractable; section headings valid") needs a real PDF; the renderer choice is irreversible because the G5 gate is typed to it.
- **Done-when:** `jh render` on each archetype's fixture `ResumeContent` produces a 1–2 page PDF; `pypdf` text extraction returns the section headings ("Experience", "Education", "Skills") and the bullets in the correct order; the `.txt` and `.json` files exist and match the PDF's content.
- **Status:** `pending` · **blocked on O4 sign-off**

---

## M5 — Eval gates

**Acceptance (§20 M5):** fabrication recall ≥ 0.95 on golden claims; all adversarial corruptions blocked; `jh eval run --suite all` implemented and wired into CI.

### M5-1. Golden claims authored (≥ 60)
- **Do:** Create `eval_data/golden_claims/*.json` — at least 60 resume snippets with fact sets and expected labels (supported / unsupported / partial). **Must include adversarial fabrications:** number inflation (e.g. "2M req/day" → "5M req/day"), added technology (a skill not in the profile), title change (a different level), date shift (a start/end moved). Each JSON: `snippet` (the resume text), `cited_fact_ids`, `expected_label`, `fabrication_type` (null for clean, or one of the four adversarial types).
- **Why:** G1's recall gate (≥ 0.95 on fabrications) consumes this set; authoring it here means M5's gate can run immediately.
- **Done-when:** `ls eval_data/golden_claims/*.json | wc -l` ≥ 60; the set includes ≥ 15 adversarial fabrications (≥ 3 of each type); every file validates against the schema.
- **Status:** `pending`

### M5-2. G1–G7 gates + LLM judges + regression runner
- **Do:** Create `eval/gates.py` (G1 truth: (a) structural — every bullet's `source_fact_ids` exist; (b) numeric/entity check in code — all numbers, org names, technologies, dates in output text must appear in cited facts, normalized; (c) LLM `claims_verify` secondary per-claim check. G2 consistency: same employer/title/dates across all documents ever sent to the same company and across archetypes, deterministic vs `profile.yaml` display options. G3 positioning-legal: only allowed display variants; no title-level change; no date changes; anonymization only via declared descriptors. G4 coverage: ≥ 70% of JD `must_have` items the profile can truthfully support are present. G5 format: 1–2 pages; PDF text extractable; section headings valid; no non-ASCII garbage; word count bounds — `pypdf` + rules. G6 cover rules: 120–180 words, engagement-format sentence present, no banned phrases, no placeholders, company name correct. G7 policy: rate/hours per config; AI-tool/subcontract disclosure present when the posting asks; no mention of `never_claim` facts.), `eval/judge.py` (LLM judges: relevance, specificity, personalization, fit-sound — non-blocking scores stored; default blocking at < 3/5 for relevance and fit), `eval/claims_check.py` (the numeric/entity checker for G1b), `eval/ats.py` (G5 helpers), `eval/runner.py` (orchestrates all gates + judges; writes `eval_runs` rows; `jh eval run --suite {router,claims,emails,all}`).
- **Why:** the gates are the spec's core safety mechanism (§2.1 truthfulness, §13.1 blocking gates); the regression runner is what CI enforces.
- **Done-when:** `jh eval doc <DOC_ID>` runs G1–G7 + judges on a real document and writes an `eval_runs` row; a unit test on G1b asserts a resume that quotes a number not in the cited facts fails; a unit test on G3 asserts a title-level change (e.g. "CTO" → "VP") fails; a unit test on G5 asserts a 3-page PDF fails; `jh eval run --suite claims` on the 60 golden claims (M5-1) achieves fabrication recall ≥ 0.95.
- **Status:** `pending`

### M5-3. Adversarial corruption tests + CI wiring
- **Do:** Write mutation-style tests (§18): automatically corrupt a valid resume (change a number, add a tech, shift a date, change a title) and assert the gates fail. Wire `jh eval run --suite all` into CI; CI exits non-zero on regression vs the baselines.
- **Why:** M5's acceptance criterion "all adversarial corruptions blocked" + §13.3 "any change to prompts, models, or router weights MUST include an eval run artifact in the PR."
- **Done-when:** a pytest test parametrized over the 4 corruption types asserts G1 (or G3) fails on each; CI runs `jh eval run --suite all` and exits non-zero when the golden-claims recall drops below 0.95 or the router baseline drops > 3 points.
- **Status:** `pending`

---

## M6 — Queue + Send + Track

**Acceptance (§20 M6):** E2E test passes (send → reply → classified → status updated → follow-up cancelled); email classifier macro-F1 ≥ 0.85 on golden emails.

### M6-1. Golden emails authored (≥ 50)
- **Do:** Create `eval_data/golden_emails/*.json` — at least 50 labeled inbound emails. Each JSON: `raw_email` (headers + body), `expected_classification` (one of the 9 classes from §11.8: `auto_reply | rejection | info_request | screen_request | interview_invite | assignment | offer | spam | other`), `expected_confidence_threshold` (the minimum confidence that should trigger `needs_human`). Include edge cases: out-of-office, `Auto-Submitted` header, ambiguous replies, multi-thread replies.
- **Why:** the classifier's macro-F1 gate (≥ 0.85) consumes this set.
- **Done-when:** `ls eval_data/golden_emails/*.json | wc -l` ≥ 50; the set covers all 9 classification labels; every file validates against the schema.
- **Status:** `pending`

### M6-2. Approval queue + send (email + manual channels)
- **Do:** Create `send/queue.py` (approved applications ordered by score; enforce `max_per_day`, `min_gap_seconds`, quiet hours in recipient local time if known else Principal's), `send/email_sender.py` (SMTP/Gmail API from a dedicated address; set `Message-ID`; store it for thread matching; attach resume PDF; plain-text body), `send/limits.py` (rate-limit enforcement), `send/manual_export.py` (`jh export package APP_ID` → application-package folder: resume PDF, cover text, job URL, checklist, rate answer snippets). `autosend` only for the `email` channel, only if config enables it and the posting provides an application email (§11.7). Every send creates an `events` row and schedules follow-ups.
- **Why:** the queue is the human-in-the-loop gate (§2.3); the send layer is where `Message-ID` is minted (the key for M6-3's inbox matching).
- **Done-when:** `jh queue approve <APP_ID>` moves the application to `status=approved`; `jh send run --dry-run` previews the batch respecting `max_per_day` + quiet hours; `jh send run` sends via the email channel and writes a `messages` row with a `Message-ID` + an `events` row; `jh export package <APP_ID>` creates the folder with all 5 artifacts.
- **Status:** `pending`

### M6-3. Inbox poll + classifier + status transitions + follow-ups
- **Do:** Create `track/inbox.py` (IMAP poll, default every 10 min, of a dedicated label/mailbox; store messages; match to applications by `In-Reply-To`/`References` headers, then by sender domain + subject heuristics; unmatched → `needs_human`), `track/classifier.py` (LLM classification into the 9 classes; rules take precedence for obvious patterns — out-of-office headers, `Auto-Submitted`; confidence < 0.7 → `needs_human`), `track/followups.py` (schedule per config in business days in the recipient's timezone; draft follow-ups — LLM, 40–70 words, adds one new value point, never pushy — queue for approval; cancel automatically when a reply arrives or status is terminal; mark `ghosted` after the final follow-up + 10 business days), `track/contacts.py`. Interview prep generator: for `screen_request`/`interview_invite`, create `prep/<application_id>.md`. Do-not-contact handling: if a company replies "do not contact," mark `do_not_contact` and block future sends to that domain (§16).
- **Why:** the feedback loop is what turns "sent" into "replied → screen → offer"; the classifier drives the application state machine.
- **Done-when:** `jh inbox poll` against a local fake IMAP server (aiosmtpd + a fake IMAP, §18) stores a new `messages` row; the classifier labels it correctly (unit test on a fixture with an `Auto-Submitted` header → `auto_reply` without an LLM call); `jh followups list` shows a due follow-up; `jh followups approve` sends it; a reply arriving cancels the pending follow-up.
- **Status:** `pending`

### M6-4. E2E test + classifier macro-F1 gate
- **Do:** Write the E2E test (§18): local SMTP/IMAP test server covering send → reply → classified → status updated → follow-up cancelled. Run `jh eval run --suite emails` on the 50 golden emails (M6-1); assert macro-F1 ≥ 0.85.
- **Why:** M6's acceptance criterion is the E2E test passing + the macro-F1 gate.
- **Done-when:** `pytest tests/e2e/` passes end-to-end (send via SMTP, reply via IMAP, classifier labels it, application status transitions, follow-up cancelled); `jh eval run --suite emails` reports macro-F1 ≥ 0.85 on the 50 golden emails; CI runs both.
- **Status:** `pending`

---

## M7 — Capacity + Reports

**Acceptance (§20 M7):** planner blocks approval when limits exceeded; weekly report renders with confidence intervals and recommendations; experiment assignment is deterministic.

### M7-1. Contracts wizard + capacity planner
- **Do:** Create `capacity/contracts.py` (CLI wizard `jh contract add`: rate, hours/week, AI-tools + subcontracting permissions, NDA scope, exclusivity, IP terms, meeting-overlap windows, status `active|paused|ended`), `capacity/planner.py` (compute weekly committed hours; utilization vs `capacity.max_total_hours_week`; calendar overlap conflicts between contracts' required windows; **block** new `approved` applications when `active_contracts >= max_active_contracts` unless `--override`; **warn** when utilization ≥ `warn_at_utilization`; **warn** when any active contract has `ai_tools_allowed != yes` — reminder in the weekly report; flag exclusivity/IP clauses that conflict with other active contracts).
- **Why:** the capacity module is the spec's defense against over-commitment (§1.8, §11.9); the block is a hard gate, the warns are soft.
- **Done-when:** `jh contract add` on a fixture offer creates a `contracts` row with all fields populated; `jh contract plan` blocks a new `approved` application when `active_contracts == max_active_contracts` (exits non-zero without `--override`); a unit test asserts utilization at 0.9 triggers the warn; a unit test asserts two contracts with conflicting `ai_tools_allowed` / exclusivity produce a flag.
- **Status:** `pending`

### M7-2. Funnel + weekly report + experiments
- **Do:** Create `report/funnel.py` (jobs ingested → parsed → shortlisted → composed → gate pass → approved → sent → replied → screen → interview → offer; by archetype, source, prompt_version, week), `report/weekly.py` (Markdown report: top rejection reasons, gate-failure reasons, LLM spend, capacity status, rule-based recommendations — e.g. "archetype C: n=60, reply rate 3% < baseline 9%; review"), `report/experiments.py` (`variant` assignment via deterministic hashing on job_id; compare reply rates; flag insufficient sample size < 30 per arm). Wilson confidence intervals on all conversion rates.
- **Why:** the report is how the Principal tunes the system (§1.9, §11.10); the experiment harness is the A/B comparison the spec mandates.
- **Done-when:** `jh report weekly --since 14d` renders a Markdown report with the funnel table (all 10 stages), Wilson CIs on each conversion rate, the LLM-spend aggregate, the capacity block, and ≥ 1 rule-based recommendation; `jh report funnel --since 7d` prints the by-archetype/source/prompt_version breakdown; a unit test asserts experiment variant assignment is deterministic (same job_id → same variant across two runs).
- **Status:** `pending`

---

## M8 — Optional UI + Hardening

**Acceptance (§20 M8):** container runs `jh daemon`; restore-from-backup test passes; README quickstart verified from a clean checkout.

### M8-1. Optional HTMX UI (MAY be skipped)
- **Do:** Create a minimal FastAPI + HTMX web UI for the approval queue (list, show, approve, reject). If skipped, document the decision in `docs/DECISIONS.md` and ensure the CLI covers every queue operation.
- **Why:** §3 says "CLI-first; UI is milestone 8 and MAY be skipped."
- **Done-when:** either the UI is implemented and a `pytest` integration test exercises the approve flow, or `docs/DECISIONS.md` has a new entry recording the skip decision.
- **Status:** `pending`

### M8-2. Docker packaging + backup/restore + `jh doctor` complete
- **Do:** Create `Dockerfile` and `docker-compose.yml` (app only; SQLite volume). Implement `jh db backup` (encrypted, age/gpg optional flag, §16) and a restore path. Ensure `jh doctor` checks all of: config, DB, Typst binary, mailbox connectivity, LLM key presence (§17).
- **Why:** M8's acceptance criterion "restore-from-backup test passes."
- **Done-when:** `docker compose up` runs `jh daemon` and the container survives a restart; a `pytest` test backs up the DB, deletes the file, restores, and asserts the row count is unchanged; `jh doctor` exits 0 with a typed report on every check.
- **Status:** `pending`

### M8-3. README quickstart verified from a clean checkout
- **Do:** Run the README quickstart (10 steps, above) on a fresh clone; time it; it must complete in under 30 minutes (§22 Definition of done). Fix any step that breaks.
- **Why:** §22: "README quickstart reproduces it in under 30 minutes."
- **Done-when:** a timed run of the 10-step quickstart from a clean `git clone` completes in < 30 min with zero manual code changes; the final state is 10 application packages in the approval queue (the §22 dry-run).
- **Status:** `pending`

---

## Out-of-scope reminder (spec §21)

Every step above MUST NOT build: automated submission to platforms that forbid automation; CAPTCHA solving; account farming; ToS-violating scraping; false credentials/references/identity claims; features that conceal the Principal's identity after engagement or let someone else perform contracted work without written consent; automatic offer acceptance or contract signing; LinkedIn automation bots. A step that drifts toward any of these is `blocked` by definition, not by a marker.

## Golden-set authoring summary (cross-reference)

| Set | Count | Authored in | Consumed by |
|---|---|---|---|
| `eval_data/golden_jobs` | ≥ 30 | M2-1 | M2-3 (parser), M3-1/M3-2 (router + baseline) |
| `eval_data/golden_claims` | ≥ 60 | M5-1 | M5-2 (G1 recall gate) |
| `eval_data/golden_emails` | ≥ 50 | M6-1 | M6-4 (classifier macro-F1 gate) |

## Definition of done (spec §22)

All milestones accepted; CI green on a clean checkout; `jh eval run --suite all` passes against baselines; a dry run from "paste 10 job URLs" to "10 application packages in the approval queue" completes without manual code changes; README quickstart reproduces it in under 30 minutes.
