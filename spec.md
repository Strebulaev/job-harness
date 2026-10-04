# SPEC: Contractor Job-Search Agent Harness ("jobharness")

Audience: an autonomous AI coding agent (e.g. Claude Code) that will implement this system end-to-end.
Owner: a single senior engineer (the "Principal") seeking independent-contractor (ICA / B2B) engagements.

---

## 0. How to use this spec

- Implement milestones in order (section 20). Do not start milestone N+1 until all acceptance criteria of N pass in CI.
- Every requirement tagged **MUST** is mandatory. **SHOULD** is strongly preferred. **MAY** is optional.
- When the spec is ambiguous, choose the simplest option that satisfies the acceptance criteria, document the decision in `docs/DECISIONS.md` (one paragraph each), and continue. Do not stall for clarification unless a decision is irreversible or touches section 2.
- Prefer boring, well-known libraries. No framework magic. No premature abstraction.

---

## 1. Product goal

Build a local-first pipeline that:

1. Ingests contractor/remote job postings from permitted sources.
2. Normalizes them into a structured schema.
3. Filters and scores them against the Principal's constraints.
4. Generates a tailored resume (PDF) and cover letter per posting, **strictly derived from a single factual profile**.
5. Gates every document through automated truthfulness and quality evals.
6. Queues approved applications for human-confirmed sending.
7. Tracks all communications and state per posting, classifies inbound email, schedules follow-ups.
8. Tracks active contract capacity so the Principal never over-commits.
9. Reports funnel metrics and supports A/B comparison of prompts and archetypes.

### 1.1 SMART target (for the Principal, informational)

- 15-20 offers within 8 weeks, ICA engagements, USD 2,000-4,000 per month, employers in Europe, CIS and USA.
- Principal works in GMT+2; required overlap with the client: at least 3 hours inside 09:00-18:00 client-local time.
- Expected funnel (to be validated by metrics): 800-1500 quality applications -> 8-12% reply/screen -> 15-20% screen-to-offer.

The harness MUST measure these rates and expose them; it MUST NOT optimize application volume at the expense of the eval gates.

---

## 2. Non-negotiable constraints (read first)

1. **Truthfulness.** All resume and cover-letter content MUST be derivable from `profile.yaml`. The system MUST NOT invent employers, titles, dates, degrees, certifications, technologies, metrics, or references. Rewording, reordering, selecting, summarizing, and omitting are allowed. Fabricating is not. A claim that cannot be traced to a profile fact MUST block the document (hard gate G1).
2. **Positioning is selection, not falsification.** Allowed: choosing which true achievements to show, hiding management/budget bullets for hands-on roles, limiting the detailed window to the last N years, anonymizing an employer by a truthful descriptor (e.g. "B2B SaaS company, ~300 employees") **while keeping the real name and dates in the profile for verification on request**. Forbidden: changing a job title to a different level, shifting dates, removing employment periods to hide gaps in a misleading way, claiming skills not in the profile.
3. **Human in the loop.** No application is sent without an explicit `approve` action by the Principal until `autosend.enabled` is true in config, and `autosend` MUST be restricted to channels where automated sending is permitted by the platform's terms. Default: disabled.
4. **Platform terms.** Ingest and send adapters MUST respect each source's ToS, robots.txt and rate limits. Prefer official APIs, RSS, email alerts, and manual-import (paste URL / paste JD). The system MUST NOT implement CAPTCHA bypass, fingerprint evasion, fake accounts, or bulk automated form submission on platforms that prohibit it. Each adapter declares `tos_notes` and `allowed_actions`.
5. **Engagement model: ICA only.** Postings that are employment-only (W-2/payroll/"full-time employee"), require exclusivity, or require fixed on-site presence are filtered out (see router hard filters).
6. **Third-party data and AI-tool policy.** For every contract the Principal accepts, a `contracts` record MUST capture whether AI tools and subcontracting are permitted and the NDA/data scope. The system MUST warn when work items would be processed by AI tools on a contract where `ai_tools_allowed` is false or unknown.
7. **Privacy.** All PII (profile, emails, resumes) stays local. Only the minimum necessary text is sent to LLM providers. No telemetry. Secrets via environment variables or OS keyring, never committed.
8. **Reproducibility.** Every generated document stores: prompt version, model id, temperature, input hashes, eval results. Any document can be regenerated and diffed.

---

## 3. Tech stack

- Python 3.12, `uv` for dependency management, `ruff` + `mypy --strict` + `pytest`.
- Pydantic v2 for all schemas and validation.
- SQLite (WAL mode) via SQLAlchemy 2.x Core/ORM + Alembic migrations. Must be portable to Postgres (no SQLite-only features in business logic).
- Typer for CLI, Rich for terminal output.
- httpx (async) for HTTP, `tenacity` for retries, `aiolimiter` for rate limiting.
- Jinja2 + Typst (preferred) or Pandoc/WeasyPrint for PDF rendering.
- LLM access through a thin provider interface (section 12). Default provider: Anthropic API via the official SDK; model ids come from config, never hard-coded.
- Retrieval: BM25 (`rank_bm25`) as baseline; optional local embeddings (`sentence-transformers`) behind a feature flag.
- Email: IMAP (read) and SMTP or Gmail API (send), behind interfaces.
- Scheduling: APScheduler in-process, or cron invoking CLI. No Celery/Redis.
- Optional minimal web UI for the approval queue (FastAPI + HTMX). CLI-first; UI is milestone 8 and MAY be skipped.
- Containerization: a `Dockerfile` and `docker-compose.yml` (app only; SQLite volume).

---

## 4. Repository layout

```
jobharness/
  pyproject.toml
  README.md
  docs/
    DECISIONS.md
    SOURCES.md              # per-source ToS notes
    PROMPTS.md              # prompt catalogue and versioning rules
  config/
    config.example.yaml
    profile.example.yaml
    archetypes/
      a_ai_llm_engineer.yaml
      b_backend_contractor.yaml
      c_automation_integration.yaml
      d_platform_devops_light.yaml
      e_technical_advisor.yaml
      f_fullstack_mvp.yaml
    positioning.example.yaml
  src/jobharness/
    __init__.py
    cli.py
    settings.py
    db/            (models.py, session.py, migrations/)
    schemas/       (profile.py, archetype.py, jd.py, documents.py, events.py)
    llm/           (provider.py, anthropic_provider.py, fake_provider.py, structured.py, prompts/)
    ingest/        (base.py, rss.py, email_alerts.py, manual.py, adapters/…)
    parse/         (jd_parser.py, normalizers.py)
    route/         (filters.py, scoring.py, router.py, overqualification.py)
    compose/       (retrieval.py, resume.py, cover.py, claims.py)
    render/        (templates/, typst_renderer.py)
    eval/          (gates.py, judge.py, golden.py, claims_check.py, ats.py, runner.py)
    send/          (queue.py, email_sender.py, limits.py, manual_export.py)
    track/         (events.py, inbox.py, classifier.py, followups.py, contacts.py)
    capacity/      (planner.py, contracts.py)
    report/        (funnel.py, experiments.py, weekly.py)
    util/          (hashing.py, time.py, text.py, logging.py)
  tests/
    unit/ integration/ e2e/ fixtures/
  eval_data/
    golden_jobs/         # 30+ labeled JDs (json)
    golden_claims/       # resume snippets with expected supported/unsupported labels
    golden_emails/       # labeled inbound emails
  scripts/
  .github/workflows/ci.yml
```

---

## 5. Configuration (`config/config.yaml`)

All values validated by a Pydantic `Settings` model; unknown keys are errors.

```yaml
paths:
  data_dir: ./data
  output_dir: ./data/out
llm:
  provider: anthropic            # anthropic | fake
  models:
    parse: "<model-id-small>"
    compose: "<model-id-strong>"
    judge: "<model-id-strong-different-prompt-role>"
    classify: "<model-id-small>"
  temperature: {parse: 0.0, compose: 0.4, judge: 0.0, classify: 0.0}
  max_retries: 3
  daily_token_budget: 2000000
  redact_pii_in_logs: true
principal:
  timezone: "Europe/Kiev"        # GMT+2 equivalent; use IANA name from the user
  work_window_local: {start: "09:00", end: "18:00"}
  min_overlap_hours: 3
  target_overlap_hours: 4
router:
  min_score_to_apply: 65
  rate_floor_usd_month: 2000
  rate_ceiling_usd_month: 4000
  allow_below_floor_if_hours_leq: 10   # optional exception
  countries_allow: []                  # empty = all
  countries_deny: []
  engagement_types_allow: [contractor, b2b, freelance, project]
send:
  autosend: {enabled: false, allowed_channels: []}
  max_per_day: 20
  min_gap_seconds: 90
  quiet_hours_local: {start: "21:00", end: "07:00"}
followups:
  schedule_business_days: [5, 10]
  max_followups: 2
capacity:
  max_total_hours_week: 40
  max_active_contracts: 3
  warn_at_utilization: 0.8
```

---

## 6. Data model (SQL)

Use these tables (types shown SQLite-style; use SQLAlchemy portable types). All tables have `id` (integer PK), `created_at`, `updated_at` (UTC ISO8601). Add indexes on every foreign key and on `jobs(status)`, `jobs(score)`, `events(application_id, ts)`.

```sql
CREATE TABLE sources (
  name TEXT PRIMARY KEY, kind TEXT, tos_notes TEXT, enabled INTEGER, last_run_at TEXT
);

CREATE TABLE jobs (
  id INTEGER PRIMARY KEY,
  source TEXT REFERENCES sources(name),
  external_id TEXT,
  url TEXT, url_hash TEXT UNIQUE,
  company TEXT, title TEXT,
  jd_raw TEXT, jd_raw_hash TEXT,
  jd_parsed_json TEXT,              -- validated against schemas/jd.py
  parse_model TEXT, parse_prompt_version TEXT,
  country TEXT, remote_policy TEXT,
  engagement_type TEXT,
  comp_min_usd_month REAL, comp_max_usd_month REAL, comp_confidence TEXT,
  overlap_hours REAL,
  ai_policy TEXT,                    -- allowed | forbidden | unknown
  subcontracting_policy TEXT,
  exclusivity INTEGER,
  score REAL, score_breakdown_json TEXT,
  archetype TEXT,
  status TEXT,                       -- new|parsed|rejected|shortlisted|composed|gated_fail|queued|approved|sent|closed
  reject_reasons_json TEXT,
  first_seen_at TEXT, last_seen_at TEXT
);

CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  job_id INTEGER REFERENCES jobs(id),
  kind TEXT,                         -- resume|cover
  archetype TEXT,
  content_json TEXT,                 -- structured content before rendering
  content_hash TEXT,
  pdf_path TEXT,
  prompt_version TEXT, model TEXT, temperature REAL,
  inputs_hash TEXT,
  eval_json TEXT, eval_pass INTEGER,
  iteration INTEGER,
  experiment_id TEXT, variant TEXT
);

CREATE TABLE applications (
  id INTEGER PRIMARY KEY,
  job_id INTEGER REFERENCES jobs(id),
  resume_doc_id INTEGER REFERENCES documents(id),
  cover_doc_id INTEGER REFERENCES documents(id),
  channel TEXT,                      -- email|platform_manual|form_manual
  status TEXT,                       -- queued|approved|sent|replied|screen|interview|offer|accepted|rejected|ghosted|withdrawn
  approved_at TEXT, sent_at TEXT,
  proposed_rate_usd_month REAL, proposed_hours_week REAL
);

CREATE TABLE contacts (
  id INTEGER PRIMARY KEY, company TEXT, name TEXT, role TEXT, email TEXT, linkedin_url TEXT, notes TEXT
);

CREATE TABLE messages (
  id INTEGER PRIMARY KEY,
  application_id INTEGER REFERENCES applications(id) NULL,
  direction TEXT,                    -- in|out
  channel TEXT, message_id_header TEXT UNIQUE, thread_id TEXT,
  from_addr TEXT, to_addr TEXT, subject TEXT, body_text TEXT, received_or_sent_at TEXT,
  classification TEXT, classification_confidence REAL, needs_human INTEGER
);

CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  application_id INTEGER REFERENCES applications(id),
  type TEXT,                         -- sent|reply|screen_scheduled|interview|offer|rejected|follow_up_sent|ghosted|note|status_change
  ts TEXT, payload_json TEXT
);

CREATE TABLE followups (
  id INTEGER PRIMARY KEY, application_id INTEGER REFERENCES applications(id),
  due_at TEXT, sequence INTEGER, status TEXT,   -- pending|drafted|sent|cancelled
  draft_doc_id INTEGER NULL
);

CREATE TABLE contracts (
  id INTEGER PRIMARY KEY,
  application_id INTEGER REFERENCES applications(id) NULL,
  company TEXT, rate_usd_month REAL, hours_week REAL,
  start_date TEXT, end_date TEXT NULL,
  ai_tools_allowed TEXT,             -- yes|no|unknown
  subcontracting_allowed TEXT,
  nda_scope TEXT, exclusivity INTEGER, ip_terms TEXT,
  overlap_window_json TEXT, status TEXT  -- active|paused|ended
);

CREATE TABLE eval_runs (
  id INTEGER PRIMARY KEY, kind TEXT, target_id INTEGER, results_json TEXT, passed INTEGER, git_sha TEXT
);

CREATE TABLE llm_calls (
  id INTEGER PRIMARY KEY, purpose TEXT, model TEXT, prompt_version TEXT,
  input_tokens INTEGER, output_tokens INTEGER, latency_ms INTEGER, cost_usd REAL,
  request_hash TEXT, ok INTEGER, error TEXT
);
```

State machine for `jobs.status` and `applications.status` MUST be enforced in code (`allowed_transitions` dict); illegal transitions raise.

---

## 7. Profile (single source of truth) — `profile.yaml`

Pydantic model `Profile`. Validation errors are fatal. Every leaf fact that may appear in a document has a stable `fact_id` (e.g. `exp.acme.2022.b3`).

```yaml
version: 1
identity:
  full_name: "…"
  public_alias: null             # optional professional alias for display; must be truthful
  email: "…"
  phone: null
  location: {city: "…", country: "…", timezone: "Europe/Kiev"}
  links: {github: null, linkedin: null, site: null}
  languages: [{lang: "English", level: "C1"}, {lang: "Russian", level: "native"}]
summary_facts:
  - {id: sum.1, text: "…", tags: [architecture, ai]}
experience:
  - id: exp.acme
    employer_real: "Acme Corp"
    employer_display_options:
      full: "Acme Corp"
      anonymized: "B2B SaaS company (~300 employees)"     # must be truthful
    title_real: "CTO"
    title_display_options:
      exact: "CTO"
      handson_descriptor: "CTO (hands-on, backend & ML)"   # descriptor, not a different level
    start: "2019-03"
    end: "2024-08"
    employment_type: "full_time"
    bullets:
      - id: exp.acme.b1
        text: "Designed event-driven ingestion pipeline handling 2M req/day; p99 latency -40%."
        tags: [backend, performance, python]
        kind: hands_on            # hands_on | leadership | strategy | budget
        metrics: [{name: "req/day", value: 2000000}, {name: "p99_latency_change", value: -0.40}]
        evidence: "internal dashboard, verifiable on request"
education: [{id: edu.1, institution: "…", degree: "…", field: "…", start: "…", end: "…"}]
certifications: [{id: cert.1, name: "…", issuer: "…", date: "…"}]
projects: [{id: prj.1, name: "…", url: null, summary: "…", tags: [], bullets: []}]
skills:
  - {id: skill.python, name: "Python", level: expert, years: 12, last_used: "2026", evidence_fact_ids: [exp.acme.b1]}
disclosure_rules:
  allow_employer_anonymization: true
  must_disclose_real_employer_on: [offer_stage, background_check]
  never_claim: ["Kubernetes certified"]    # explicit negative facts
```

Rules:
- `skills[].evidence_fact_ids` MUST reference existing bullets. A skill without evidence MAY exist but is flagged `weak` and not listed in "core skills" unless the JD requires it AND `skill.level >= working`.
- `kind` drives positioning dial suppression (section 9).
- A CLI command `profile validate` MUST check: unique ids, date ordering, no overlapping full-time roles unless flagged `concurrent: true`, every referenced id exists, anonymized descriptors present when `allow_employer_anonymization`.
- `profile lint` SHOULD warn about unverifiable metrics (no `evidence`).

---

## 8. Archetypes — `config/archetypes/*.yaml`

```yaml
id: a_ai_llm_engineer
name: "AI/LLM Application Engineer"
headline_templates:
  - "AI/LLM Application Engineer — RAG, agents, evaluation"
must_have_keywords: [llm, rag, python, evaluation]
nice_to_have_keywords: [langchain, vector db, fine-tuning, agents, mcp]
jd_match_signals: [llm, "language model", rag, agent, prompt, embeddings]
fact_selection:
  prefer_tags: [ai, llm, rag, python, evals]
  suppress_kinds: [strategy, budget]
  max_bullets_per_role: {recent: 5, older: 2}
cover_letter:
  proof_points_tags: [ai, evals]
  avoid_phrases: ["passionate", "rockstar", "ninja"]
rate_guidance_usd_month: {min: 2500, max: 4000}
typical_hours_week: [15, 30]
```

Create six archetypes: A AI/LLM application, B backend, C automation/integration, D platform/DevOps (light), E technical advisor/fractional, F full-stack MVP. Archetypes MUST be data-driven; adding a new one MUST NOT require code changes.

---

## 9. Positioning — `positioning.yaml`

```yaml
target_level: senior_ic        # mid | senior_ic | staff_ic
suppress_kinds_default: [strategy, budget]
leadership_visibility: minimal # none | minimal | full
recency_window_years: 10       # detailed roles within window; older compressed to one line
employer_display: anonymized   # full | anonymized
title_display: handson_descriptor   # exact | handson_descriptor
rate_expectation_usd_month: {min: 2000, max: 4000}
hours_week: {min: 15, max: 30}
engagement_label: "Independent contractor (ICA/B2B)"
```

**Overqualification module** (`route/overqualification.py`): compute `gap = principal_level - posting_level` (levels from parsed JD: seniority and comp band mapped to an ordinal 1-5). If `gap >= 2`: set composer mode `handson_focus`, enable the one-sentence "format rationale" in the cover letter (hands-on contractor, focused scope, part-time), and lower leadership visibility. All adjustments are recorded in `documents.content_json.positioning_applied`.

---

## 10. JD schema — `schemas/jd.py`

```python
class JDParsed(BaseModel):
    title: str
    company: str | None
    seniority: Literal["intern","junior","mid","senior","staff","principal","lead","unknown"]
    engagement_type: Literal["employee","contractor","b2b","freelance","project","unknown"]
    exclusivity: Literal["required","preferred","none","unknown"]
    remote_policy: Literal["remote","hybrid","onsite","unknown"]
    onsite_required: bool | None
    countries_allowed: list[str]          # ISO-3166 alpha-2, empty if unrestricted/unknown
    timezone_requirements: str | None     # verbatim snippet
    required_overlap: dict | None         # {"tz":"America/New_York","start":"09:00","end":"13:00"}
    hours_per_week: tuple[float,float] | None
    compensation: dict | None             # {"min":float,"max":float,"currency":str,"period":"hour|month|year|project"}
    must_have: list[str]                  # normalized skills/requirements
    nice_to_have: list[str]
    tech_stack: list[str]
    responsibilities: list[str]
    ai_tools_policy: Literal["allowed","forbidden","unknown"]
    subcontracting_policy: Literal["allowed","forbidden","unknown"]
    red_flags: list[str]                  # e.g. "unpaid trial", "equity only", "exclusive", "9-18 on site", "test project w/o pay"
    application_method: Literal["email","platform","form","unknown"]
    application_email: str | None
    evidence_spans: dict[str, str]        # field -> verbatim snippet from JD supporting it
```

Parser rules:
- The LLM MUST return JSON only; validate with Pydantic; on failure retry up to 2 times with the validation error appended; then mark job `parse_failed`.
- Every non-"unknown" categorical field SHOULD have an `evidence_spans` entry; the parser post-check verifies the span is a substring of `jd_raw` (case-insensitive, whitespace-normalized); otherwise set the field to `unknown`.
- Currency conversion to USD/month in code (`normalizers.py`) using a config table of static FX rates with a `fx_as_of` date (MAY be refreshed manually). Hourly -> month via `hours_week` or default 120 h/month with `comp_confidence="low"`.

---

## 11. Pipeline modules

### 11.1 Ingest (`ingest/`)

Interface:

```python
class SourceAdapter(Protocol):
    name: str
    tos_notes: str
    allowed_actions: set[Literal["fetch","send"]]
    async def fetch(self, since: datetime | None) -> AsyncIterator[RawJob]: ...
```

- `RawJob`: source, external_id, url, title, company?, jd_text, posted_at?, raw_payload.
- Mandatory adapters: `manual` (CLI: `jh job add --url … [--paste]`), `rss` (generic feed list in config), `email_alerts` (parse job-alert emails from IMAP label), plus 2-3 API/RSS-based adapters from the list in `docs/SOURCES.md` (examples: Remote OK, We Work Remotely, Himalayas, Working Nomads, Wellfound alerts, Habr Career, djinni alerts). Each adapter MUST be implemented only if the source permits programmatic access; otherwise implement as `email_alerts` or `manual`.
- Dedup: `url_hash` (canonicalized URL) and `jd_raw_hash`; fuzzy duplicate detection (company+title+similarity >= 0.92) links duplicates to the first job.
- Rate limiting per adapter; User-Agent identifies the tool; honor `robots.txt` and cache with ETag/If-Modified-Since.
- Output: insert `jobs` with `status=new`.

### 11.2 Parse (`parse/`)
As section 10. Batch with concurrency limit (default 4). Cache by `(jd_raw_hash, prompt_version, model)`.

### 11.3 Router (`route/`)

**Hard filters** (any failure -> `status=rejected`, reasons stored):
1. `engagement_type == employee` -> reject; `unknown` -> keep with penalty and flag `verify_engagement`.
2. `exclusivity == required` -> reject.
3. `onsite_required == True` -> reject.
4. Country allow/deny lists.
5. Overlap: compute overlap between Principal's work window (timezone from config) and the posting's required window (or default 09:00-18:00 in the company's primary timezone if inferable). `overlap_hours < min_overlap_hours` -> reject; if posting timezone unknown -> keep with flag.
6. Compensation: if known and `max < rate_floor` (adjusted for hours) -> reject. If unknown -> keep with flag `ask_rate`.
7. `ai_tools_policy == forbidden` -> reject (configurable).
8. Red-flag blocklist (unpaid trial, equity-only, "pay to apply"), configurable regex list.

**Scoring** (0-100, weights in config; return breakdown):
- Stack match (30): weighted overlap between JD `must_have`/`tech_stack` and profile skills (with level and recency).
- Rate fit (20): position of the posting range relative to `rate_expectation`.
- TZ/overlap (15).
- Engagement fit (10): explicit contractor/B2B > unknown.
- Scope/hours fit (10).
- Company/posting quality signals (10): clear JD, named hiring contact, funded/known company (from JD text only; no external scraping by default).
- Overqualification penalty (up to -15) when expected rate cannot be met.

Archetype selection: score each archetype by `jd_match_signals` and keyword overlap; choose max; store top-2 with scores. If top score < threshold -> `rejected: no_archetype`.

Shortlist: `score >= router.min_score_to_apply` -> `status=shortlisted`.

### 11.4 Compose (`compose/`)

Inputs: `Profile`, `Archetype`, `Positioning`, `JDParsed`, `Job`.

**Resume composition algorithm:**
1. Candidate facts = all bullets/projects/skills.
2. Filter by positioning (`suppress_kinds`, recency window, leadership visibility).
3. Retrieve and rank facts by relevance to the JD: BM25 over `text+tags` against `must_have + tech_stack + responsibilities`; MAY blend embeddings. Apply archetype `prefer_tags` boost. Keep within `max_bullets_per_role`.
4. Select skills: JD-required skills present in profile first (level >= working), then archetype nice-to-have; hard cap 12.
5. LLM step (structured output): given ONLY the selected facts (with ids) produce `ResumeContent` where every bullet carries `source_fact_ids: list[str]`. The LLM may rephrase and merge facts, may reorder, MUST NOT add numbers/entities/technologies not present in the cited facts. Headline from archetype templates, parameterized with JD title keywords where truthful.
6. Employer/title display chosen by positioning; the real values stay in an internal `verification_block` that is **not** rendered but stored.
7. Output `ResumeContent` JSON; render later.

`ResumeContent` schema: `header`, `headline`, `summary` (<= 3 lines), `skills_core`, `experience[{employer_display,title_display,start,end,bullets[{text,source_fact_ids}]}]`, `earlier_experience_line`, `education`, `certifications`, `projects`, `languages`, `positioning_applied`.

**Cover letter:**
- 120-180 words, plain text.
- Structure: (1) one specific observation about the company/product drawn from JD text (no outside scraping unless user-provided notes exist), (2) one proof point from a cited fact, (3) one sentence on engagement format: independent contractor, expected hours/week, rate expectation, (4) call to action.
- Each factual sentence carries `source_fact_ids` (internal).
- If overqualification mode is on, include exactly one sentence of format rationale.
- Banned phrases list from archetype + global list (clichés).
- Rate expectation inclusion is configurable per source (`include_rate: true|false|if_requested`).

Regeneration loop: on gate failure, feed structured failure feedback to the composer for up to `max_iterations=2`; afterwards `status=gated_fail` and the job enters the manual review queue.

### 11.5 Render (`render/`)
- Typst template (preferred) producing a single-column ATS-safe PDF: standard fonts, no tables for layout, no icons, no images, real text layer, section headings from a fixed vocabulary ("Experience", "Education", "Skills").
- Output also a `.txt` and `.json` of the same content.
- A test renders each archetype with fixture data and asserts PDF text extraction (via `pypdf`) returns headings and bullets in order.

### 11.6 Eval (`eval/`) — see section 13.

### 11.7 Send (`send/`)
- Queue: approved applications ordered by score; enforce `max_per_day`, `min_gap_seconds`, quiet hours (recipient local time if known, else Principal's).
- Channels:
  - `email`: send via SMTP/Gmail API from a dedicated address; sets `Message-ID`, stores it for thread matching; attach resume PDF; plain-text body.
  - `platform_manual` / `form_manual`: generate an "application package" folder (resume PDF, cover text, job URL, checklist, rate answer snippets) and open it for the Principal; the Principal marks `sent` via CLI after submitting. No automated form submission.
- `autosend` only for `email` channel and only if config enables it and the posting provides an application email.
- Every send creates an `events` row and schedules follow-ups.

### 11.8 Track (`track/`)
- `inbox.py`: IMAP poll (default every 10 min) of a dedicated label/mailbox; store messages; match to applications by `In-Reply-To`/`References` headers, then by sender domain + subject heuristics; unmatched go to `needs_human`.
- `classifier.py`: LLM classification into `auto_reply | rejection | info_request | screen_request | interview_invite | assignment | offer | spam | other` with confidence; rules take precedence for obvious patterns (out-of-office headers, `Auto-Submitted`). Confidence < 0.7 -> `needs_human`.
- Status updates: classification drives application status transitions via the state machine; every change writes an `events` row.
- `followups.py`: schedule per config in **business days** in the recipient's timezone; draft follow-ups (LLM, 40-70 words, adds one new value point; never pushy), queue for approval; cancel automatically when a reply arrives or status is terminal; mark `ghosted` after the final follow-up + 10 business days.
- Interview prep generator: for `screen_request`/`interview_invite`, create `prep/<application_id>.md` with JD summary, sent resume, likely questions per archetype, rate/hours negotiation notes (from config), logistics.

### 11.9 Capacity (`capacity/`)
- On `offer`/`accepted`, prompt to create a `contracts` record (CLI wizard) capturing rate, hours/week, AI-tools and subcontracting permissions, NDA scope, exclusivity, IP terms, and meeting-overlap windows.
- Planner computes weekly committed hours, utilization vs `capacity.max_total_hours_week`, calendar overlap conflicts between contracts' required windows, and warns/blocks:
  - Block new `approved` applications when `active_contracts >= max_active_contracts` unless `--override`.
  - Warn when utilization >= `warn_at_utilization`.
  - Warn when any active contract has `ai_tools_allowed != yes` (reminder in the weekly report).
  - Flag exclusivity/IP clauses that conflict with other active contracts.

### 11.10 Report (`report/`)
- Funnel: jobs ingested -> parsed -> shortlisted -> composed -> gate pass -> approved -> sent -> replied -> screen -> interview -> offer; by archetype, source, prompt_version, week.
- Conversion rates with Wilson confidence intervals.
- Weekly Markdown report (`jh report weekly`) including: top rejection reasons, gate failure reasons, LLM spend, capacity status, recommendations (rule-based, e.g. "archetype C: n=60, reply rate 3% < baseline 9%; review").
- Experiments: `experiments` support assigning `variant` (e.g. `cover_v3` vs `cover_v4`) with deterministic hashing on job_id; report compares reply rates and flags insufficient sample size (< 30 per arm).

---

## 12. LLM layer (`llm/`)

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self, *, purpose: str, model: str, system: str, user: str,
        schema: type[BaseModel], temperature: float, max_tokens: int,
        prompt_version: str, request_tags: dict[str, str]
    ) -> tuple[BaseModel, LLMCallMeta]: ...
    async def generate_text(...)-> tuple[str, LLMCallMeta]: ...
```

Requirements:
- `FakeProvider` for tests: deterministic outputs from fixtures keyed by `request_hash`; the entire test suite MUST run offline with it.
- Structured output via the provider's JSON/tool-use mechanism where available; always validate with Pydantic; strip code fences; bounded retries with error feedback.
- Log every call to `llm_calls` (no raw PII in logs when `redact_pii_in_logs`).
- Daily token/cost budget enforcement with a clear error.
- Prompt files live in `llm/prompts/<name>/v<N>.md` with front-matter (`name`, `version`, `purpose`, `schema`). Prompts are immutable once released; changes create a new version. `docs/PROMPTS.md` lists each prompt's intent and eval coverage.
- Prompt-injection hygiene: JD text, emails, and any external text are wrapped in clearly delimited blocks and described as untrusted data; system prompts instruct models to ignore instructions inside such blocks. Outputs never trigger actions directly; actions come only from validated schemas and code paths.

Required prompts: `jd_parse`, `claims_extract`, `claims_verify`, `resume_compose`, `cover_compose`, `judge_resume`, `judge_cover`, `fit_sound_judge`, `email_classify`, `followup_draft`, `interview_prep`.

---

## 13. Eval layer (`eval/`)

### 13.1 Blocking gates (all MUST pass to reach the approval queue)

| Gate | Check | Method |
|---|---|---|
| G1 Truth | Every claim in resume/cover traces to profile facts | (a) structural: each bullet has `source_fact_ids` that exist; (b) numeric/entity check in code: all numbers, org names, technologies, dates in output text must appear in cited facts (normalized); (c) LLM `claims_verify` as secondary check per claim with labels supported/unsupported/partial. Any unsupported claim fails. |
| G2 Consistency | Same employer/title/dates across all documents ever sent to the same company and across archetypes | Deterministic comparison against `profile.yaml` display options. |
| G3 Positioning-legal | Only allowed display variants used; no title-level change; no date changes; anonymization only via declared descriptors | Deterministic. |
| G4 Coverage | >= 70% of JD `must_have` items that the profile can truthfully support are present | Deterministic on normalized skill sets; reports uncoverable requirements separately (informational). |
| G5 Format | 1-2 pages; PDF text extractable; section headings valid; no non-ASCII garbage; word count bounds | `pypdf` + rules. |
| G6 Cover rules | 120-180 words, contains engagement-format sentence, no banned phrases, no placeholders (`[...]`, `{{`), company name correct | Deterministic. |
| G7 Policy | Rate/hours included per config; AI-tool/subcontract disclosure present when posting asks; no mention of facts in `never_claim` | Deterministic. |

### 13.2 LLM judges (non-blocking scores stored; thresholds configurable, default blocking at < 3/5 for relevance and fit)
- Relevance to archetype and JD (1-5).
- Specificity and measurability of bullets (1-5).
- Personalization of cover letter (1-5).
- Fit-sound: "too senior/expensive | on target | too junior" for this posting. If `too senior`, composer is re-run once with `handson_focus`.
- Judges use a different system prompt and, where possible, a different model than the composer; temperature 0; the rubric is included in the prompt; outputs are JSON with rationale.

### 13.3 Golden sets and regression
- `eval_data/golden_jobs`: >= 30 JDs with labels (`apply: yes/no`, `archetype`, `expected_reject_reasons`). Metrics: router precision/recall, archetype accuracy. CI fails if precision drops > 3 points vs. the stored baseline.
- `eval_data/golden_claims`: >= 60 resume snippets with fact sets and expected labels; measures G1 detector recall on injected fabrications (include adversarial: number inflation, added tech, title change, date shift). Required recall >= 0.95 on fabrications.
- `eval_data/golden_emails`: >= 50 labeled emails; classifier macro-F1 >= 0.85.
- `jh eval run --suite all` prints a table and exits non-zero on regression. Any change to prompts, models, or router weights MUST include an eval run artifact in the PR.

### 13.4 Online metrics
Computed by `report/`; include reply rate, screen rate, offer rate per archetype/source/prompt version, time-to-first-reply, gate-failure rate, manual-override rate (how often the Principal edits documents before approving — a key quality signal).

---

## 14. CLI (`jh`)

```
jh init                         # create dirs, DB, copy example configs
jh profile validate|lint|show
jh ingest run [--source NAME] [--since 7d]
jh job add --url URL [--paste]  # manual import
jh parse run [--limit N]
jh route run [--explain JOB_ID]
jh compose run [--job JOB_ID | --all-shortlisted] [--variant NAME]
jh eval doc DOC_ID | jh eval run --suite {router,claims,emails,all}
jh queue list|show APP_ID|edit APP_ID|approve APP_ID|reject APP_ID|approve-batch --min-score N
jh send run [--dry-run]
jh sent mark APP_ID            # for manual channels
jh inbox poll
jh followups list|draft|approve
jh contract add|list|plan      # capacity
jh report funnel|weekly [--since]
jh export package APP_ID       # application package folder
jh db backup
```
All commands: `--json` output option, non-zero exit on error, idempotent where reasonable, `--dry-run` where side effects exist.

---

## 15. Scheduling

- `jh daemon` (APScheduler): ingest hourly; parse+route after ingest; compose for shortlisted nightly and on demand; inbox poll every 10 min; follow-up scheduler hourly; weekly report Monday 08:00 local.
- All jobs idempotent and resumable; single-instance lock file.

---

## 16. Security, privacy, compliance

- Secrets in env/keyring; `.env` git-ignored; `detect-secrets` pre-commit hook.
- Encrypt DB backups (age/gpg) optional flag.
- PII redaction utility for logs and LLM request logging.
- Dedicated mailbox/domain with SPF/DKIM/DMARC documented in README; do not use the Principal's primary inbox.
- Respect unsubscribe/stop requests: if a company replies "do not contact", mark `do_not_contact` and block future sends to that domain.
- GDPR hygiene: `jh contacts purge --company X` removes personal data of a recipient on request.
- Never store third-party confidential code/data from contracts in this system; the `contracts` table stores metadata only.

---

## 17. Observability and quality

- Structured logging (JSON) with run ids; `jh doctor` checks config, DB, Typst binary, mailbox connectivity, LLM key presence.
- Metrics counters persisted in DB (no external services).
- Error taxonomy: `ParseError`, `GateFailure`, `PolicyViolation`, `RateLimit`, `ProviderError`; each with actionable messages.

---

## 18. Testing strategy

- Unit tests for filters, scoring, overlap calculation (include DST edge cases for US/EU timezones), compensation normalization, business-day scheduling, state machine, claims numeric/entity checker.
- Property tests (Hypothesis) for: overlap computation symmetry/bounds; `ResumeContent` never includes numbers absent from cited facts after the G1 checker passes.
- Integration tests with `FakeProvider` and fixture JDs through ingest -> parse -> route -> compose -> eval -> render -> queue.
- E2E test with a local SMTP/IMAP test server (e.g. `aiosmtpd` + a fake IMAP) covering send, reply matching, classification, follow-up cancel.
- Mutation-style adversarial tests: automatically corrupt a valid resume (change a number, add a tech, shift a date, change a title) and assert gates fail.
- Coverage target >= 85% on `route`, `eval`, `compose/claims`, `track`.
- CI: ruff, mypy --strict, pytest, offline eval suites, build Docker image.

---

## 19. Documentation deliverables

- `README.md`: quickstart (10 steps max), architecture diagram (Mermaid), CLI reference, safety constraints summary.
- `docs/SOURCES.md`: one entry per adapter (access method, ToS summary, rate limits, allowed actions).
- `docs/PROMPTS.md`, `docs/DECISIONS.md`.
- `docs/RUNBOOK.md`: daily workflow for the Principal (morning: review queue; midday: inbox; weekly: report and prompt/archetype tuning).

---

## 20. Milestones and acceptance criteria

**M1 — Foundations.** Repo, config/settings, DB + migrations, profile/archetype/positioning schemas, `profile validate|lint`, state machines, FakeProvider, CI.
Accept: `jh init && jh profile validate` passes on example files; mypy/ruff/pytest green.

**M2 — Ingest + Parse.** Manual, RSS, email-alert adapters (+ 1-2 permitted API adapters), dedup, JD parser with evidence-span verification, normalizers.
Accept: 30 golden JDs parse into valid `JDParsed` offline with FakeProvider fixtures; dedup tests pass; evidence-span verification demonstrably downgrades unsupported fields.

**M3 — Router.** Hard filters, scoring, archetype selection, overqualification module, `--explain` output.
Accept: golden-jobs router precision >= 0.85 and recall >= 0.80 on fixture labels; explain output lists each filter/score component.

**M4 — Compose + Render.** Retrieval, resume and cover composition, positioning, PDF rendering.
Accept: for each archetype, a fixture job produces a 1-2 page ATS-safe PDF; every bullet has valid `source_fact_ids`; deterministic regeneration from stored inputs.

**M5 — Eval gates.** G1-G7, judges, regression runner, adversarial corruption tests.
Accept: fabrication recall >= 0.95 on golden claims; all adversarial corruptions blocked; `jh eval run --suite all` implemented and wired into CI.

**M6 — Queue + Send + Track.** Approval queue, rate limits, email sending, package export, inbox polling, classification, status transitions, follow-ups, do-not-contact handling.
Accept: E2E test passes (send -> reply -> classified -> status updated -> follow-up cancelled); email classifier macro-F1 >= 0.85 on golden emails.

**M7 — Capacity + Reports.** Contracts wizard, planner warnings/blocks, funnel and weekly report, experiments.
Accept: planner blocks approval when limits exceeded; weekly report renders with confidence intervals and recommendations; experiment assignment is deterministic.

**M8 — Optional UI + Hardening.** HTMX approval queue, Docker packaging, backup/restore, `jh doctor`, docs complete.
Accept: container runs `jh daemon`; restore-from-backup test passes; README quickstart verified from a clean checkout.

---

## 21. Out of scope (do NOT build)

- Automated submission to platforms that forbid automation; CAPTCHA solving; account farming; scraping that violates ToS.
- Generating, storing or sending any false credential, reference, or identity claim.
- Any feature that conceals the Principal's identity from a client after engagement begins, or that lets someone other than the contracted party perform contracted work without the client's written consent.
- Automatic acceptance of offers or signing of contracts.
- LinkedIn automation bots.

---

## 22. Definition of done

All milestones accepted; CI green on a clean checkout; `jh eval run --suite all` passes against baselines; a dry run from "paste 10 job URLs" to "10 application packages in the approval queue" completes without manual code changes; README quickstart reproduces it in under 30 minutes.