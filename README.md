# jobharness

Local-first contractor job-search agent harness. Ingests permitted job postings, normalizes them, scores them against the Principal's constraints, generates a tailored resume (PDF) and cover letter per posting strictly derived from a single factual profile, gates every document through automated truthfulness and quality evals, queues approved applications for human-confirmed sending, and tracks all communications, state, and active-contract capacity.

Full spec: [`spec.md`](spec.md). Decision log: [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Quickstart (≤ 10 steps)

> Assumptions: Python 3.12, `uv` installed, `typst` binary on PATH (or Pandoc as fallback — see `docs/DECISIONS.md` O4), a dedicated mailbox + LLM provider key in the environment.

1. **Clone and install deps.**
   ```bash
   git clone <repo> jobharness && cd jobharness
   uv sync
   ```
2. **Initialize the workspace.** Creates `data/`, the SQLite DB (WAL mode), and copies example configs.
   ```bash
   uv run jh init
   ```
3. **Fill in your profile.** Edit `config/profile.yaml` (copy from `config/profile.example.yaml`). Every leaf fact that may appear in a document has a stable `fact_id`.
   ```bash
   uv run jh profile validate   # fatal on error
   uv run jh profile lint       # warns on unverifiable metrics
   ```
4. **Pick the LLM provider + model ids** (irreversible — see `docs/DECISIONS.md` O2). Edit `config/config.yaml`:
   ```yaml
   llm:
     provider: anthropic
     models:
       parse: <small-model-id>
       compose: <strong-model-id>
       judge: <strong-model-id>
       classify: <small-model-id>
   ```
   Set the provider key in the environment (e.g. `ANTHROPIC_API_KEY`).
5. **Confirm the two API adapters** (irreversible — see `docs/DECISIONS.md` O1). The spec mandates 1–2 permitted API/RSS adapters in addition to `manual`, `rss`, and `email_alerts`. Edit `config/config.yaml` to add the chosen feeds/APIs and record their ToS in `docs/SOURCES.md`.
6. **Pick the PDF renderer** (O4). Default: Typst. If you prefer Pandoc/WeasyPrint, set the flag in `config/config.yaml` before M4.
7. **Run the doctor check.**
   ```bash
   uv run jh doctor   # config, DB, Typst binary, mailbox connectivity, LLM key
   ```
8. **Ingest + parse + route.**
   ```bash
   uv run jh ingest run --source all --since 7d
   uv run jh parse run --limit 50
   uv run jh route run --explain <JOB_ID>   # inspect one job's filters + score breakdown
   ```
9. **Compose + gate + queue.**
   ```bash
   uv run jh compose run --all-shortlisted
   uv run jh eval doc <DOC_ID>             # run G1-G7 on one document
   uv run jh queue list                    # see the approval queue
   ```
10. **Approve + send.**
    ```bash
    uv run jh queue approve <APP_ID>
    uv run jh send run --dry-run
    uv run jh send run
    ```

That's the loop. Day-to-day, follow [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Architecture (Mermaid)

```mermaid
flowchart LR
  subgraph Ingest
    M[manual]:::src
    R[rss]:::src
    EA[email_alerts]:::src
    A1[API-1]:::src
    A2[API-2]:::src
  end
  subgraph Pipeline
    P[parse<br/>JDParsed]:::mod
    RT[route<br/>hard filters + scoring<br/>archetype + overqualification]:::mod
    C[compose<br/>retrieval + LLM<br/>ResumeContent / cover]:::mod
    RD[render<br/>Typst → PDF + .txt + .json]:::mod
    EV[eval<br/>G1-G7 gates + LLM judges]:::mod
  end
  subgraph Delivery
    Q[send/queue<br/>max_per_day, quiet hours]:::mod
    S[email | platform_manual<br/>form_manual]:::mod
  end
  subgraph Feedback
    TB[track<br/>inbox poll + classifier<br/>follow-ups + status]:::mod
    CP[capacity<br/>contracts + planner]:::mod
    RP[report<br/>funnel + weekly + experiments]:::mod
  end
  subgraph Knowledge
    PROF[profile.yaml<br/>single source of truth]:::data
    ARCH[config/archetypes/*.yaml<br/>6 archetypes]:::data
    POS[positioning.yaml]:::data
    LLM[llm/<br/>provider + prompts vN]:::data
  end
  M --> P
  R --> P
  EA --> P
  A1 --> P
  A2 --> P
  P --> RT
  RT --> C
  PROF --> C
  ARCH --> C
  POS --> C
  LLM --> C
  C --> RD
  RD --> EV
  EV -->|pass| Q
  EV -->|fail: gated_fail| C
  Q --> S
  S --> TB
  TB --> CP
  S --> RP
  TB --> RP
  CP --> RP
  classDef src fill:#e8f0fe,stroke:#4285f4
  classDef mod fill:#f3e8fe,stroke:#a142f4
  classDef data fill:#fff3e0,stroke:#ffa726
```

## CLI reference

Full reference: spec §14. Summary:

| Group | Commands | Notes |
|---|---|---|
| Setup | `jh init` | Create dirs, DB, copy example configs. Idempotent. |
| Profile | `jh profile validate` · `jh profile lint` · `jh profile show` | `validate` is fatal on error; `lint` warns. |
| Ingest | `jh ingest run [--source NAME] [--since 7d]` · `jh job add --url URL [--paste]` | Manual import via `--paste`. |
| Parse | `jh parse run [--limit N]` | Batch concurrency 4; cache by `(jd_raw_hash, prompt_version, model)`. |
| Route | `jh route run [--explain JOB_ID]` | Hard filters + scoring + archetype + overqualification. |
| Compose | `jh compose run [--job JOB_ID \| --all-shortlisted] [--variant NAME]` | Regeneration loop up to `max_iterations=2` on gate failure. |
| Eval | `jh eval doc DOC_ID` · `jh eval run --suite {router,claims,emails,all}` | `all` exits non-zero on regression. |
| Queue | `jh queue list` · `show APP_ID` · `edit APP_ID` · `approve APP_ID` · `reject APP_ID` · `approve-batch --min-score N` | Human-in-the-loop gate. |
| Send | `jh send run [--dry-run]` · `jh sent mark APP_ID` | `--dry-run` previews; manual channels via `sent mark`. |
| Inbox | `jh inbox poll` | IMAP poll, default every 10 min under `jh daemon`. |
| Follow-ups | `jh followups list` · `draft` · `approve` | Business-day scheduling in recipient's timezone. |
| Contracts | `jh contract add` · `list` · `plan` | Capacity wizard + planner. |
| Reports | `jh report funnel` · `weekly [--since]` | Wilson CIs; rule-based recommendations. |
| Export | `jh export package APP_ID` | Application-package folder for manual channels. |
| Ops | `jh db backup` · `jh doctor` | Encrypted backup; env/config/mailbox/LLM checks. |

All commands: `--json` output option, non-zero exit on error, idempotent where reasonable, `--dry-run` where side effects exist.

## Safety constraints (from spec §2, non-negotiable)

1. **Truthfulness.** All resume/cover content MUST be derivable from `profile.yaml`. No invented employers, titles, dates, degrees, certifications, technologies, metrics, or references. G1 blocks any document with an unsupported claim.
2. **Positioning is selection, not falsification.** Allowed: choosing which true achievements to show, limiting the detailed window to the last N years, anonymizing an employer by a truthful descriptor (keeping the real name + dates in the profile for verification). Forbidden: changing a job title to a different level, shifting dates, removing employment periods to hide gaps in a misleading way, claiming skills not in the profile.
3. **Human in the loop.** No application is sent without an explicit `approve` action until `send.autosend.enabled` is `true` (default: `false`).
4. **Platform terms.** No CAPTCHA bypass, no fingerprint evasion, no fake accounts, no bulk automated form submission. Each adapter declares `tos_notes` and `allowed_actions` (see `docs/SOURCES.md`).
5. **ICA only.** Employment-only, exclusivity-required, or fixed on-site postings are hard-filtered.
6. **Third-party data + AI-tool policy.** Every accepted contract records whether AI tools and subcontracting are permitted and the NDA/data scope. The system warns when work items would be processed by AI tools on a contract where `ai_tools_allowed` is `no` or `unknown`.
7. **Privacy.** All PII stays local. Minimum necessary text sent to LLM providers. No telemetry. Secrets via environment variables or OS keyring, never committed.
8. **Reproducibility.** Every generated document stores prompt version, model id, temperature, input hashes, eval results. Any document can be regenerated and diffed.

## Out of scope (spec §21)

The system MUST NOT build: automated submission to platforms that forbid automation; CAPTCHA solving; account farming; ToS-violating scraping; false credentials/references/identity claims; features that conceal the Principal's identity after engagement or let someone else perform contracted work without written consent; automatic offer acceptance or contract signing; LinkedIn automation bots.

## Repository layout

See spec §4. Top-level: `pyproject.toml`, `README.md` (this file), `spec.md`, `docs/` (DECISIONS, SOURCES, PROMPTS, RUNBOOK, plans/), `config/` (config.example.yaml, profile.example.yaml, archetypes/ ×6, positioning.example.yaml), `src/jobharness/` (cli, settings, db/, schemas/, llm/, ingest/, parse/, route/, compose/, render/, eval/, send/, track/, capacity/, report/, util/), `tests/` (unit/, integration/, e2e/, fixtures/), `eval_data/` (golden_jobs/, golden_claims/, golden_emails/), `scripts/`, `.github/workflows/ci.yml`.

## Implementation status

See `docs/plans/changeset-implementation-plan.md` for the milestone-ordered (M1→M8) step list with per-step status markers. The two irreversible items (adapter count O1, LLM provider/model choice O2) are flagged there and in `docs/DECISIONS.md`.
