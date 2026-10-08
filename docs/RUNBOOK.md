# RUNBOOK — daily use from Telegram

This is the operating manual for the Telegram bot (decision 0014). The bot only talks to you; nothing is sent to employers.

## Prerequisites

- The bot is running (`docker compose up -d`) and `jh doctor` reports no missing environment variables.
- You completed setup once: `/profile_start`, `/preferences`, `/connect openrouter`, `/models set ...` for parse, classify, compose and judge, a source (`/connect superjob` and/or `/feed_add <url>`), then `/run`.
- `JH_MASTER_KEY` is backed up somewhere safe. Without it, stored keys cannot be decrypted.

## Daily (about 5 minutes)

1. Open the chat. Each new match is a message with title, company, match score, flags and the job link, followed by the resume file and the cover letter.
2. Read the resume and cover letter. Edit them as you like and apply on the job's own site or by email yourself.
3. Press **Applied** or **Skip** on the message so the job is never suggested again.
4. `/status` shows whether the search is active, the last cycle, deliveries today and tokens used against the daily budget.

## Weekly

1. `/profile` — check the profile is complete; add new roles or accomplishments with `/profile_role` (true facts only; metrics need evidence).
2. `/preferences` — adjust rate, hours, countries or the search interval if results are too many or too few.
3. `/feeds` — remove feeds that produce noise (`/feed_remove`).
4. `/models` — review the models; a stronger compose model usually improves letters, a cheaper parse model lowers cost.

## When something is off

- **No jobs arrive:** `/status` shows the last cycle and any error; `/search_now` runs one cycle immediately. Check `/providers` and `/feeds`.
- **A key stops working:** `/connect <provider>` again with a new key.
- **Daily token budget reached:** the bot says so and pauses LLM work until tomorrow; raise `llm.daily_token_budget` in `config/config.yaml` if intended.
- **Jobs failing quality checks:** `/status` counts them; they are not delivered. Usually the profile lacks matching facts, so add them with `/profile_role` or `/profile_skills`.
- **Stop everything:** `/pause`. Remove stored keys with `/disconnect openrouter` and `/disconnect superjob`.

## Safety reminders (from §2, non-negotiable)

- **Truthfulness.** Nothing appears on a resume or letter that is not derivable from your profile. Gate G1 blocks unsupported claims.
- **You apply.** The bot never contacts employers.
- **Platform terms.** Only add feeds whose terms allow automated reading; the SuperJob terms are not yet verified (`docs/SOURCES.md`).
- **Keys.** Pasted keys are deleted from the chat at once and stored encrypted; never share `JH_MASTER_KEY`.
