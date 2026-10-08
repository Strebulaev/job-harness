# PROMPTS — catalogue and versioning rules

Source: spec §12. Prompts live in `src/jobharness/llm/prompts/<name>/v<N>.md` with front-matter (`name`, `version`, `purpose`, `schema`). **Prompts are immutable once released; changes create a new version.** This file lists each prompt's intent and eval coverage.

## Versioning rules

- Every prompt file has front-matter: `name`, `version`, `purpose`, `schema` (the Pydantic model the structured output must validate against).
- A released prompt (one that has ever produced a `documents` row or an `eval_runs` row) is **immutable**. A change creates `v<N+1>` and the old version stays on disk.
- Every `documents` row stores `prompt_version` + `model` + `temperature` + `inputs_hash` (§6, §2.8 reproducibility). Every `llm_calls` row stores `prompt_version` + `model` + `request_hash` (§6).
- Any change to a prompt, a model, or a router weight MUST include an eval-run artifact in the PR (§13.3). CI fails if router precision drops > 3 points vs. the stored baseline.
- Prompt-injection hygiene (§12): JD text, emails, and any external text are wrapped in clearly delimited blocks and described as untrusted data; system prompts instruct the model to ignore instructions inside such blocks. Outputs never trigger actions directly; actions come only from validated schemas and code paths.

## Catalogue

| Prompt | Purpose | Schema (Pydantic) | Temperature | Eval coverage |
|---|---|---|---|---|
| `jd_parse` | Parse a raw JD into `JDParsed` | `JDParsed` (§10) | 0.0 (§5) | `golden_jobs` ≥ 30; parser post-check verifies every non-"unknown" categorical field has an `evidence_spans` entry that is a substring of `jd_raw` (§10). |
| `claims_extract` | *(not used in the MVP: claims are extracted by code, `compose/claims.py`)* | — | — | G1 structural check (a): every bullet has `source_fact_ids` that exist. |
| `claims_verify` | Secondary per-claim check: supported / unsupported / partial | `ClaimsVerifyOutput` | 0.0 | `golden_claims`; G1 check (c); fabrication recall ≥ 0.95 on injected fabrications (number inflation, added tech, title change, date shift). |
| `resume_compose` | Given ONLY selected facts (with ids), rewrite bullets; each carries `source_fact_ids`. Code assembles the rest of `ResumeContent` and validates every bullet, falling back to the original text | `ResumeDraft` (`schemas/documents.py`) | 0.4 (§5) | G1–G5 gates; property test: after G1 passes, `ResumeContent` never includes numbers absent from cited facts (§18). |
| `cover_compose` | Observation, proof point and closing; code adds the engagement-format sentence and checks 120–180 words (§11.4) | `CoverDraft` | 0.4 (§5) | G6, G7 gates; banned-phrase check; engagement-format sentence present. |
| `judge_resume` | LLM judge: relevance + specificity (1–5) | `JudgeScores` | 0.0 | Non-blocking scores stored; default blocking threshold < 3/5. |
| `judge_cover` | LLM judge: personalization (1–5) | `JudgeScores` | 0.0 | Same as above. |
| `fit_sound_judge` | "too senior/expensive \| on target \| too junior" for this posting | `FitJudgement` | 0.0 | If `too senior`, composer re-runs once with `handson_focus` (§13.2). |
| `email_classify` *(deferred, plan 7.1)* | Classify inbound email into 9 classes (§11.8) | (internal) | 0.0 | `golden_emails` ≥ 50; macro-F1 ≥ 0.85; confidence < 0.7 → `needs_human`. |
| `followup_draft` *(deferred, plan 7.1)* | 40–70 word follow-up; adds one new value point; never pushy (§11.8) | (internal) | 0.4 (§5) | Manual review in the approval queue; no golden set (low-risk, human-gated). |
| `interview_prep` *(deferred, plan 7.1)* | Generate `prep/<application_id>.md` for `screen_request`/`interview_invite` (§11.8) | (markdown) | 0.4 (§5) | Manual review; no golden set. |

## Roles → model mapping (config-driven, O2)

`config/config.yaml` §5 maps four prompt purposes to model ids:

| Purpose | Model id (from config) | Temperature |
|---|---|---|
| `parse` | `llm.models.parse` (small) | 0.0 |
| `compose` | `llm.models.compose` (strong) | 0.4 |
| `judge` | `llm.models.judge` (strong, different prompt role) | 0.0 |
| `classify` | `llm.models.classify` (small) | 0.0 |

Judges use a different system prompt and, where possible, a different model than the composer (§13.2). The `judge` role is intentionally separate from `compose` so the composer cannot game its own judge.

## FakeProvider

For tests: `FakeProvider` returns deterministic outputs keyed by `request_hash` from fixtures in `tests/fixtures/`. The entire test suite MUST run offline with it (§12, §18). A cold agent writing tests MUST NOT hit a real LLM provider.

## Providers

`llm.provider` is `openrouter` (decision 0015), `anthropic` or `fake`. OpenRouter calls go to `https://openrouter.ai/api/v1/chat/completions` with the key from the encrypted store; structured output uses `response_format: json_schema` (support varies by model and upstream provider, so requests set `provider.require_parameters`) and is always re-validated with Pydantic. `provider.data_collection: deny` is sent by default; both provider preference keys are unverified against the live API (plan step 3.1). In the Telegram bot, the four model ids are chosen with `/models set <role> <model-id>` and stored in `data/user_settings.yaml`.

`ScriptedProvider` (`llm/scripted_provider.py`) is the offline test double keyed by prompt purpose, used by the pipeline, bot and end-to-end tests next to `FakeProvider`.
