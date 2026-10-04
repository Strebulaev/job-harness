# RUNBOOK — Principal's daily / weekly workflow

Source: spec §19 (daily workflow) and §14 (CLI). This is the operating manual, not the implementation spec. The implementing agent should treat this file as *read-only reference* — the commands listed here must exist and behave as described by the time M8 is accepted.

## Prerequisites

- `config/config.yaml` is valid (`jh doctor` passes).
- LLM provider key is in the environment or OS keyring (never in a file). See `docs/DECISIONS.md` O2 for the provider choice.
- A dedicated mailbox/domain with SPF/DKIM/DMARC is configured (§16). Do **not** use the Principal's primary inbox.
- `jh init` has been run at least once (creates `data/`, DB, example configs).

## Morning (~15 min)

1. `jh inbox poll` — pull new inbound email from the dedicated label; the classifier runs and writes `messages` rows.
2. `jh queue list --json` — see the approval queue (applications with `status=queued`).
3. For each queued application: `jh queue show <APP_ID>` → read the resume PDF, cover letter, score breakdown, gate results.
4. Approve: `jh queue approve <APP_ID>` (or `jh queue approve-batch --min-score N` for a bulk pass on a trusted day). Reject: `jh queue reject <APP_ID>` with a reason.
5. `jh report funnel --since 7d` — check the last week's funnel; look for gate-failure spikes or a reply-rate drop on one archetype.

## Midday (~10 min)

1. `jh send run --dry-run` — preview what would be sent today, respecting `max_per_day`, `min_gap_seconds`, and quiet hours.
2. If the dry-run looks right: `jh send run`. For `platform_manual` / `form_manual` channels: `jh export package <APP_ID>` opens the application-package folder; submit manually; then `jh sent mark <APP_ID>`.
3. `jh followups list` — see due follow-ups; `jh followups draft` then `jh followups approve` for any that are ready.
4. Check `needs_human` items (low-confidence classifications, unmatched inbox messages): `jh queue show` the related application if one exists.

## Weekly (Monday, ~30 min)

1. `jh report weekly --since 14d` — the Markdown report includes:
   - Funnel by archetype / source / prompt_version / week.
   - Conversion rates with Wilson confidence intervals.
   - Top rejection reasons + gate-failure reasons.
   - LLM spend (`llm_calls` aggregates).
   - Capacity status (utilization vs `capacity.max_total_hours_week`, active-contract count vs `max_active_contracts`).
   - Rule-based recommendations (e.g. "archetype C: n=60, reply rate 3% < baseline 9%; review").
2. Review the recommendations; tune archetypes (`config/archetypes/*.yaml`) or prompt versions (see `docs/PROMPTS.md`) as needed. A prompt change requires a new version + an eval-run artifact in the PR (§13.3).
3. `jh contract list` — review active contracts; confirm no contract has `ai_tools_allowed != yes` that the weekly report flagged.
4. `jh db backup` — encrypted backup (age/gpg optional, §16).

## On an offer

1. `jh contract add` — CLI wizard captures rate, hours/week, AI-tools + subcontracting permissions, NDA scope, exclusivity, IP terms, meeting-overlap windows.
2. `jh contract plan` — the capacity planner recomputes weekly committed hours, utilization, calendar overlaps; it blocks new `approved` applications when `active_contracts >= max_active_contracts` unless `--override` (§11.9).

## Safety reminders (from §2, non-negotiable)

- **Truthfulness.** No resume/cover letter content may appear that is not derivable from `profile.yaml`. G1 blocks any document with an unsupported claim.
- **Human in the loop.** No application is sent without an explicit `approve` action until `send.autosend.enabled` is `true` (default: `false`).
- **Platform ToS.** No CAPTCHA bypass, no fingerprint evasion, no fake accounts, no bulk automated form submission. See `docs/SOURCES.md`.
- **PII stays local.** Only the minimum necessary text is sent to LLM providers. No telemetry.
