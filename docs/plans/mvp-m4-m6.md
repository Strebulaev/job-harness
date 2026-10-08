# MVP plan — M4 to M6 (compose, gate, send, track)

Goal: bring jobharness to MVP, defined in decision `docs/decisions/0013-mvp-is-m1-to-m6-offline.md` as spec §20 milestones M1–M6 accepted, proven offline on fixtures. M1–M3 are done. This plan covers M4–M6, the MVP close-out, and three post-MVP steps. M7 and M8 are out of scope.

This plan is not a decision, fact, guardrail or procedure. It has no `track` and no `expires`. Its only status is the per-step marker.

## Read this first (cold session)

- **Project:** local-first contractor job-search harness. Spec: `spec.md` (section numbers below refer to it). Decision log: `docs/DECISIONS.md` (frozen) and `docs/decisions/`. Facts: `docs/facts/`. Guardrails: `docs/guardrails/`.
- **Stack:** Python 3.12, `uv`, pydantic v2, SQLAlchemy 2 + Alembic (SQLite WAL), Typer CLI `jh` in `src/jobharness/cli.py`, pytest, ruff, `mypy --strict`. Run everything through `uv run`.
- **Already built (M1–M3):** config/settings (`src/jobharness/settings.py`), schemas (`schemas/profile.py`, `jd.py`, `archetype.py`, `positioning.py`), DB models for `jobs`, `documents`, `applications`, `contacts`, `messages`, `events`, `followups`, `contracts`, `eval_runs`, `llm_calls` (`db/models.py`, migration `alembic/versions/0001_initial_schema.py`), state machines (`db/state_machine.py`), LLM layer (`llm/`: `provider.py`, `anthropic_provider.py`, `fake_provider.py`, `structured.py`, `prompts.py`, `prompt_versions.py`, prompt files under `llm/prompts/<name>/v1.md`), ingest, parse, router (`route/`). CLI commands that exist: `init`, `doctor`, `profile validate|lint|show`, `parse run`, `job add`, `ingest run`, `route run`, `eval run` (router suite only).
- **Not built yet (stub packages with only `__init__.py`):** `compose/`, `render/`, `eval/`, `send/`, `track/`, `capacity/`, `report/`. `tests/e2e/` has only `.gitkeep`.
- **Test fixtures for LLM calls:** `FakeProvider` returns outputs keyed by request hash from `tests/fixtures/llm/`. `scripts/gen_parse_fixtures.py` shows how fixtures are generated; follow the same pattern for new prompts. The whole suite MUST run offline.
- **Hard rules (spec §2, decisions 0013 and 0012, guardrail `docs/guardrails/mvp-gates-offline-only.md`):**
  - No test or acceptance command may need a live LLM key or network.
  - Generated resume and cover content must be derivable from the profile; never invent employers, titles, dates, metrics or technologies. Use `config/profile.example.yaml` (Acme/Globex data) for all fixtures.
  - Nothing is sent without an explicit `approve`; `send.autosend.enabled` stays `false` by default.
  - PDFs are rendered with the `typst` binary on PATH (decision 0012).
  - `config/config.yaml` model ids are placeholders (`<model-id-small>` etc.). Do not pin real ids in MVP steps.
- **After every step:** `uv run ruff check src/ tests/ && uv run mypy && uv run pytest tests/unit tests/integration -q` must stay green. Update the step marker below in place, with the date and a one-line summary.
- **Markers:** `[ ]` pending, `[~]` in progress, `[x]` done, `[!]` blocked, `[>]` moved. `‖` after a marker means the step can run in parallel with other ready steps.

## Open decisions

- None block the MVP. Typst is signed off (0012). Model ids stay placeholders until step 5.2.

---

## 0. Prerequisites

### 0.1 Install Typst in CI only — [ ]
Class: implement · Needs: none · Check: `grep -n -i typst .github/workflows/ci.yml`
Context: Decision 0012 picks the Typst binary. The Principal chose to install it in CI only, not on the dev machine (`which typst` prints nothing there). `jh doctor` (`src/jobharness/cli.py`, around line 124) already checks `shutil.which("typst")`, so locally it will report typst missing; that is expected. `.github/workflows/ci.yml` has no Typst step, so M4 render tests would fail in CI.
Do: add a step to `.github/workflows/ci.yml` before the `Pytest` step that installs a pinned recent Typst release (for example the `typst-community/setup-typst` action, or a release tarball download). Do not install Typst locally. Render-dependent tests (steps 1.4, 1.5, 2.2 G5, 4.2) must use `pytest.mark.skipif(shutil.which("typst") is None, ...)` so they skip locally and run in CI. Note in the README quickstart that local rendering needs Typst on PATH, installed by the user if wanted.
Done-when: `.github/workflows/ci.yml` contains a Typst install step before the pytest step with a pinned version; the README notes the local requirement.

---

## 1. M4 — Compose and render

Acceptance (spec §20 M4): for each of the six archetypes, a fixture job produces a 1–2 page ATS-safe PDF; every bullet has valid `source_fact_ids`; regeneration from stored inputs is deterministic.

### 1.1 Document schemas and fact retrieval — [~]
Status note (2026-10-08): code and tests written (`schemas/documents.py`, `compose/retrieval.py`, `tests/unit/test_retrieval.py`, plus a `rank_bm25` mypy override in `pyproject.toml`) but NOT run — `uv` is not installed on the dev machine and its Python is 3.14. Run the Check and the full ruff/mypy/pytest suite, fix anything that fails, then mark `[x]`.
Class: implement · Needs: none · Check: `uv run pytest tests/unit/test_retrieval.py -q`
Context: Spec §11.4 steps 1–4. Profile facts (summary, experience bullets, projects, skills) each have a stable `fact_id` (`src/jobharness/schemas/profile.py`; example data in `config/profile.example.yaml`). Archetypes (`config/archetypes/*.yaml`, `schemas/archetype.py`) carry `prefer_tags` and bullet limits; positioning (`config/positioning.example.yaml`, `schemas/positioning.py`) carries `suppress_kinds`, recency window and leadership visibility. `JDParsed` is in `schemas/jd.py`. `rank-bm25` is already a dependency.
Do: create `src/jobharness/schemas/documents.py` with `ResumeContent` per spec §11.4 (`header`, `headline`, `summary` ≤ 3 lines, `skills_core`, `experience[{employer_display, title_display, start, end, bullets[{text, source_fact_ids}]}]`, `earlier_experience_line`, `education`, `certifications`, `projects`, `languages`, `positioning_applied`) plus an internal `verification_block` holding real employer, title and dates, and a `CoverLetter` model (text plus per-sentence `source_fact_ids`). Create `src/jobharness/compose/retrieval.py`: candidate facts → positioning filter → BM25 over `text+tags` against JD `must_have + tech_stack + responsibilities` → archetype `prefer_tags` boost → cap at `max_bullets_per_role` → skill selection (JD-required skills present in the profile first, then archetype nice-to-have, hard cap 12). Embeddings stay out of MVP.
Done-when: `tests/unit/test_retrieval.py` covers positioning filtering, prefer-tag boost, bullet cap, skill cap of 12 and JD-required-first ordering, and passes; `ResumeContent` rejects a bullet with empty `source_fact_ids`.

### 1.2 Resume composer and claim extraction — [ ]
Class: implement · Needs: 1.1 · Check: `uv run pytest tests/unit/test_resume_compose.py -q`
Context: Spec §11.4 steps 5–7. The LLM step receives ONLY the selected facts with their ids and returns structured `ResumeContent`; it may rephrase, merge and reorder but must not add numbers, entities or technologies absent from the cited facts. Real employer and title stay in the unrendered `verification_block`. Add prompt `resume_compose` v1 (temperature 0.4, prompt rules in `docs/PROMPTS.md`: front-matter `name`, `version`, `purpose`, `schema`; prompts are immutable once released; external text wrapped as untrusted data). Register it in `llm/prompt_versions.py`. Claims extraction feeds gate G1 (step 2.2).
Do: create `src/jobharness/compose/resume.py` (algorithm above), `src/jobharness/compose/claims.py` (extract atomic claims per bullet from `ResumeContent`), and `src/jobharness/llm/prompts/resume_compose/v1.md`. Store the result as a `documents` row with `prompt_version`, `model`, `temperature`, `inputs_hash`. Generate FakeProvider fixtures for the six archetype fixture jobs in `tests/fixtures/llm/` following `scripts/gen_parse_fixtures.py`. Add `jh compose run [--job JOB_ID | --all-shortlisted] [--variant NAME]` to `src/jobharness/cli.py` (new `compose_app`, `--json`, `--dry-run` not needed).
Done-when: `tests/unit/test_resume_compose.py` asserts every bullet's `source_fact_ids` exist in the example profile; asserts two runs with the same inputs give byte-identical JSON; asserts `verification_block` holds the real employer and title and that no rendered field does; `uv run jh compose run --job <fixture job id> --json` works against a FakeProvider config.

### 1.3 Cover letter composer — [ ] ‖
Class: implement · Needs: 1.1 · Check: `uv run pytest tests/unit/test_cover_compose.py -q`
Context: Spec §11.4 cover letter rules: 120–180 words, plain text, four parts (specific JD observation, one proof point from a cited fact, engagement-format sentence with independent contractor, expected hours/week and rate expectation, call to action); each factual sentence carries `source_fact_ids`; overqualification mode adds exactly one format-rationale sentence (see `route/overqualification.py`); banned phrases from the archetype plus a global cliché list; rate inclusion follows `include_rate: true|false|if_requested` per source. No outside scraping.
Do: create `src/jobharness/compose/cover.py` and prompt `src/jobharness/llm/prompts/cover_compose/v1.md` (temperature 0.4); register in `llm/prompt_versions.py`; add global banned-phrase list as a module constant; add FakeProvider fixtures. Hook into `jh compose run` so one run produces both documents.
Done-when: unit tests assert 120–180 words, presence of the engagement-format sentence, no banned phrase, no placeholder text (`[...]`, `{{`), correct company name, exactly one extra sentence in overqualification mode, and `source_fact_ids` on every factual sentence.

### 1.4 Typst renderer — [ ]
Class: implement · Needs: 0.1, 1.2 · Check: `uv run pytest tests/unit/test_render.py -q` (skips locally without `typst`; real proof is the CI run)
Context: Spec §11.5. Single-column ATS-safe PDF: standard fonts, no layout tables, no icons or images, real text layer, headings from the fixed vocabulary "Experience", "Education", "Skills". Also write a `.txt` and `.json` of the same content. `pypdf` is already a dependency and is used for text extraction in tests and gate G5.
Do: create `src/jobharness/render/templates/resume.typ`, `src/jobharness/render/typst_renderer.py` (calls the `typst` binary via `subprocess`, no shell; writes PDF, `.txt`, `.json` under `data/`), and `jh render` command (or fold into `jh compose run`; keep a standalone `jh render --document DOC_ID`). Rendering must be deterministic for the same input.
Done-when (verified in CI; the tests skip locally when `typst` is absent, per 0.1): for each of the six archetypes, rendering a fixture `ResumeContent` yields a 1–2 page PDF; `pypdf` extraction returns "Experience", "Education" and "Skills" headings with bullets in order; `.txt` and `.json` exist and match the PDF content.

### 1.5 M4 acceptance test across archetypes — [ ]
Class: implement · Needs: 1.2, 1.3, 1.4 · Check: `uv run pytest tests/integration/test_compose_render.py -q`
Context: M4 acceptance in spec §20; integration pattern in spec §18 (fixture JDs through parse → route → compose → render with FakeProvider).
Do: write `tests/integration/test_compose_render.py` parametrized over the six archetypes: fixture job → composed resume and cover → PDF. Add a property test (Hypothesis) that `ResumeContent` text never contains numbers absent from the cited facts once the structural check passes (this becomes G1b in step 2.2; here use a simple number-in-cited-facts helper).
Done-when: the test passes for all six archetypes; it asserts page count 1–2, valid `source_fact_ids`, and byte-identical regeneration from stored inputs.

---

## 2. M5 — Eval gates

Acceptance (spec §20 M5): fabrication recall ≥ 0.95 on golden claims; all adversarial corruptions blocked; `jh eval run --suite all` implemented and wired into CI.

### 2.1 Golden claims set (≥ 60) — [ ] ‖
Class: implement · Needs: none · Check: `uv run pytest tests/unit/test_golden_claims.py -q`
Context: Spec §13.3. Decision 0005 says golden sets are authored as plan steps. Fact 0009 says golden loaders skip `baseline.json` and `expected_downgrades.json`; keep that convention for any sidecar file. Facts come from `config/profile.example.yaml` only.
Do: create `eval_data/golden_claims/*.json`, at least 60 files, each with `snippet`, `cited_fact_ids`, `expected_label` (`supported`, `unsupported`, `partial`) and `fabrication_type` (null for clean, or `number_inflation`, `added_tech`, `title_change`, `date_shift`). Include at least 15 fabrications, at least 3 of each type. Add a schema validator (`scripts/validate_golden_claims.py` and `tests/unit/test_golden_claims.py`) modelled on `scripts/validate_golden_jobs.py`.
Done-when: `ls eval_data/golden_claims/*.json | wc -l` ≥ 60 (excluding any sidecar); the test confirms ≥ 15 fabrications with ≥ 3 per type and that every file validates.

### 2.2 Gates G1–G7 — [ ]
Class: implement · Needs: 1.2, 1.3, 1.4 · Check: `uv run pytest tests/unit/test_gates.py -q`
Context: Spec §13.1. G1 truth: (a) every bullet's `source_fact_ids` exist; (b) in code, all numbers, org names, technologies and dates in output text appear in the cited facts after normalization; (c) LLM `claims_verify` secondary check labelling supported/unsupported/partial, with any unsupported claim failing. G2 consistency of employer/title/dates across documents sent to the same company and across archetypes. G3 positioning-legal (only declared display variants, no title-level change, no date changes). G4 coverage ≥ 70% of JD `must_have` items the profile can truthfully support. G5 format (1–2 pages, extractable text, valid headings, no non-ASCII garbage, word-count bounds). G6 cover rules (see 1.3). G7 policy (rate/hours per config; AI-tool and subcontract disclosure when the posting asks; no `never_claim` facts).
Do: create `src/jobharness/eval/gates.py`, `eval/claims_check.py` (G1b), `eval/ats.py` (G5 helpers using `pypdf`), and prompts `claims_extract` and `claims_verify` v1 (temperature 0.0) with FakeProvider fixtures.
Done-when: unit tests show a resume quoting a number not in its cited facts fails G1b; a title change (for example CTO → VP) fails G3; a 3-page PDF fails G5; a cover letter with a banned phrase fails G6; each gate has a passing case on the M4 fixtures.

### 2.3 Judges and eval runner — [ ]
Class: implement · Needs: 2.1, 2.2 · Check: `uv run jh eval run --suite claims --json`
Context: Spec §13.2–13.3. Judges (`judge_resume`, `judge_cover`, `fit_sound_judge`) are non-blocking scores stored with the run; default blocking threshold < 3/5 for relevance and fit; judges use a different system prompt than the composer, temperature 0, JSON output with rationale. Regeneration loop (spec §11.4): on gate failure feed structured feedback to the composer up to `max_iterations=2`, then set `status=gated_fail` and route to manual review; if the fit judge says `too senior`, re-run the composer once with `handson_focus`. Today `jh eval run` supports only `--suite router` (`src/jobharness/cli.py`, `eval_run`). Config model ids are placeholders, so judges run through FakeProvider only.
Do: create `eval/judge.py`, `eval/runner.py` (orchestrates gates and judges, writes `eval_runs` rows, compares to stored baselines, exits non-zero on regression), prompts `judge_resume`, `judge_cover`, `fit_sound_judge` v1; extend `jh eval run --suite {router,claims,emails,all}`; add `jh eval doc DOC_ID`. The `emails` suite reports "skipped: no golden emails" until step 3.1 lands; `all` skips absent suites but fails on a regression in any present suite. Store a claims baseline file next to the golden set.
Done-when: `uv run jh eval run --suite claims --json` reports fabrication recall ≥ 0.95 on the golden claims; `uv run jh eval doc <DOC_ID>` writes an `eval_runs` row; the regeneration loop sets `gated_fail` after two failed iterations in a unit test.

### 2.4 Adversarial corruption tests and CI wiring — [ ]
Class: implement · Needs: 2.3 · Check: `uv run pytest tests/unit/test_adversarial.py -q && uv run jh eval run --suite all --json`
Context: Spec §18 mutation-style tests and §13.3 ("`jh eval run --suite all` exits non-zero on regression"). Current CI (`.github/workflows/ci.yml`) runs only `jh eval run --suite router --json`.
Do: write `tests/unit/test_adversarial.py` parametrized over four corruptions (number change, added technology, date shift, title change) applied to a valid fixture resume, asserting G1 or G3 fails each. Change the CI router step to `uv run jh eval run --suite all --json`. Add a test that `all` exits non-zero when golden-claims recall is forced below 0.95 or router precision drops more than 3 points.
Done-when: the adversarial tests pass; `.github/workflows/ci.yml` runs `--suite all`; the regression test passes.

---

## 3. M6 — Queue, send, track

Acceptance (spec §20 M6): E2E test passes (send → reply → classified → status updated → follow-up cancelled); classifier macro-F1 ≥ 0.85 on golden emails.

### 3.1 Golden emails set (≥ 50) — [ ] ‖
Class: implement · Needs: none · Check: `uv run pytest tests/unit/test_golden_emails.py -q`
Context: Spec §11.8 and §13.3. Nine classes: `auto_reply`, `rejection`, `info_request`, `screen_request`, `interview_invite`, `assignment`, `offer`, `spam`, `other`.
Do: create `eval_data/golden_emails/*.json`, at least 50, each with `raw_email` (headers and body), `expected_classification`, `expected_confidence_threshold`. Cover all nine labels; include out-of-office, an `Auto-Submitted` header case, ambiguous replies, multi-thread replies, and a "do not contact" reply. Add a validator and test modelled on 2.1. All data is synthetic; use no real names or addresses.
Done-when: ≥ 50 files; all nine labels present; every file validates.

### 3.2 Approval queue and send — [ ]
Class: implement · Needs: 2.3 · Check: `uv run pytest tests/unit/test_send.py -q`
Context: Spec §11.7 and §2.3. Only documents that pass the gates reach the queue. Config already has `send.autosend`, `max_per_day` and `quiet_hours_local` (`config/config.example.yaml`); inspect it for `min_gap_seconds`. Application statuses and legal transitions are in `db/state_machine.py`. Local SMTP for tests: `aiosmtpd` (dev dependency).
Do: create `send/queue.py` (approved applications ordered by score; enforce `max_per_day`, `min_gap_seconds`, quiet hours in recipient local time if known else the Principal's), `send/limits.py`, `send/email_sender.py` (SMTP; sets and stores `Message-ID`; attaches the resume PDF; plain-text body), `send/manual_export.py` (`jh export package APP_ID` → folder with resume PDF, cover text, job URL, checklist, rate-answer snippets). Add CLI: `jh queue list|show|edit|approve|reject|approve-batch --min-score N`, `jh send run [--dry-run]`, `jh sent mark APP_ID`, `jh export package APP_ID`. Autosend applies only to the `email` channel, only when config enables it and the posting gives an application email. Every send writes an `events` row and schedules follow-ups.
Done-when: unit tests show `approve` moves an application to `approved`; `send run --dry-run` previews a batch honoring `max_per_day` and quiet hours without sending; `send run` against a local aiosmtpd server delivers one message and writes a `messages` row with a `Message-ID` and an `events` row; `export package` creates a folder with all five artifacts.

### 3.3 Inbox poll, classifier, status transitions, follow-ups — [ ]
Class: implement · Needs: 3.2 · Check: `uv run pytest tests/unit/test_track.py -q`
Context: Spec §11.8 and §16 (do-not-contact). Matching key is the `Message-ID` stored by 3.2. Classification drives application status via the state machine and every change writes an `events` row. Rules take precedence over the LLM for obvious patterns (out-of-office headers, `Auto-Submitted`); confidence < 0.7 → `needs_human`. Follow-ups use business days in the recipient's timezone; draft by LLM (40–70 words, adds one new value point, never pushy), queued for approval; cancelled on reply or terminal status; `ghosted` after the final follow-up plus 10 business days.
Do: create `track/inbox.py` (IMAP poll; match by `In-Reply-To`/`References`, then sender domain and subject heuristics; unmatched → `needs_human`), `track/classifier.py` with prompt `email_classify` v1 (temperature 0.0), `track/followups.py` with prompt `followup_draft` v1 (temperature 0.4), `track/contacts.py`, interview-prep generator writing `prep/<application_id>.md` for `screen_request` and `interview_invite` (prompt `interview_prep` v1). Do-not-contact: mark `do_not_contact` and block future sends to that domain. CLI: `jh inbox poll`, `jh followups list|draft|approve`. For tests, use a fake IMAP server fixture under `tests/fixtures/` (spec §18: aiosmtpd plus a fake IMAP).
Done-when: unit tests show a message with an `Auto-Submitted` header is labelled `auto_reply` with no LLM call; `inbox poll` against the fake IMAP stores a `messages` row matched to its application; `followups list` shows a due follow-up and `followups approve` sends it; a reply cancels the pending follow-up; a do-not-contact reply blocks later sends to that domain.

### 3.4 E2E test and classifier gate — [ ]
Class: implement · Needs: 3.1, 3.3 · Check: `uv run pytest tests/e2e -q && uv run jh eval run --suite emails --json`
Context: M6 acceptance. Spec §18 E2E: local SMTP/IMAP server covering send, reply matching, classification, follow-up cancel. CI must run both.
Do: write `tests/e2e/test_send_reply_track.py` (send → reply → classified → status updated → follow-up cancelled); implement the `emails` suite in `eval/runner.py` (macro-F1 on the golden emails, baseline stored next to the set); add `tests/e2e` to the CI pytest step (`uv run pytest tests/unit tests/integration tests/e2e -q`).
Done-when: the E2E test passes; `jh eval run --suite emails` reports macro-F1 ≥ 0.85 on the golden emails; `.github/workflows/ci.yml` runs `tests/e2e`.

---

## 4. MVP close-out

### 4.1 Docs and status sync — [ ]
Class: implement · Needs: 2.4, 3.4 · Check: `uv run ruff check src/ tests/ && uv run mypy && uv run pytest tests/unit tests/integration tests/e2e -q`
Context: Decision 0006 says a doc is done when it has the spec-named sections. `docs/facts/docs-manifest.md` maps doc sections to watch paths. `docs/PROMPTS.md` catalogues prompts; `docs/RUNBOOK.md` lists `jh` commands that must exist.
Do: add the new prompts (`resume_compose`, `cover_compose`, `claims_extract`, `claims_verify`, `judge_resume`, `judge_cover`, `fit_sound_judge`, `email_classify`, `followup_draft`, `interview_prep`) to `docs/PROMPTS.md` if any are missing; confirm every command named in `docs/RUNBOOK.md` Morning and Midday sections exists in `jh --help` output (ones for M7 such as `report` and `contract` stay post-MVP; note that in the RUNBOOK); update the README implementation-status paragraph and CLI table; fix `docs/DECISIONS.md` pointers only if a stub changed; update fact `0012` (CI checks) in `docs/facts/0012-ci-enforced-checks.md` for the new CI steps; refresh `last-verified` in `docs/facts/docs-manifest.md` for edited docs.
Done-when: the full check passes; every `jh` command in RUNBOOK Morning/Midday exists; fact 0012 lists the Typst step, `--suite all` and `tests/e2e`.

### 4.2 MVP dry run: ten job URLs to ten queued packages — [ ]
Class: review · Needs: 4.1 · Check: `uv run pytest tests/e2e/test_mvp_dry_run.py -q`
Context: Spec §22 definition of done includes "a dry run from 'paste 10 job URLs' to '10 application packages in the approval queue' completes without manual code changes." For the MVP gate this runs on fixtures with FakeProvider and the example profile, from a clean checkout state.
Do: write `tests/e2e/test_mvp_dry_run.py`: add ten fixture jobs with `jh job add --paste` (or the equivalent function calls), then parse, route, compose, render, gate, and assert ten applications reach the approval queue with PDFs and passing eval rows. Then verify manually, in a fresh CI run (Typst is installed only there, per 0.1), that the README quickstart steps through the queue run without code edits (offline config with `llm.provider: fake`).
Done-when: the test passes; a fresh CI run of the README quickstart steps reaches `jh queue list` with ten packages; MVP is then declared by marking decision 0013's fitness functions satisfied in this plan's header.

---

## 5. Post-MVP (not part of the gate)

### 5.1 Replace the example profile with real facts — [ ]
Class: implement · Needs: 4.2 · Check: `uv run jh profile validate && uv run jh profile lint`
Context: Human-only. Truthfulness (spec §2.1) means an agent must not author career facts. `config/profile.yaml` currently mirrors the Acme/Globex example.
Do: the Principal fills `config/profile.yaml` with real facts, each leaf with a stable `fact_id`.
Done-when: `jh profile validate` passes and `jh profile lint` shows no unresolved warnings.

### 5.2 Pin real model ids and record live baselines — [ ]
Class: implement · Needs: 4.2 · Check: `! grep -q '<model-id' config/config.yaml`
Context: IRREVERSIBLE once prompt v1 baselines are recorded against a model (decision 0008, fact 0013). Needs a provider key in the environment. Fixture-based baselines from the MVP must be re-recorded.
Do: with the Principal's explicit confirmation of the four ids, set `llm.models.{parse,compose,judge,classify}` in `config/config.yaml`; run the live eval suites; record new baselines; update fact 0013 and decision 0008.
Done-when: no placeholder remains in `config/config.yaml`; `uv run jh eval run --suite all --json` passes against freshly recorded baselines.

### 5.3 Live mailbox smoke test — [ ]
Class: implement · Needs: 4.2 · Data: confidential · Check: `uv run jh doctor --json`
Context: Needs a dedicated mailbox with SPF/DKIM/DMARC (spec §16), never the Principal's primary inbox. The mailbox credentials are confidential.
Do: configure mailbox credentials through environment variables; send one approved test message to an address the Principal controls; reply; run `jh inbox poll` and confirm matching and classification.
Done-when: `jh doctor` reports mailbox connectivity ok and the reply is matched to its application.
