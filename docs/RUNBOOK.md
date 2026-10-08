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

## Operations (the host)

Commands run on the machine that hosts the container, from the repository directory.

**Install / first start**
1. `cp .env.example .env`, fill in `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID`, `JH_MASTER_KEY`.
2. `docker compose up -d --build`
3. `docker compose exec jobharness jh doctor` — every check except `db` (created on first start) should be `ok`. `typst` must be `ok` in the container, otherwise resumes arrive as text files instead of PDF.

**Logs and health**
- `docker compose logs -f jobharness` shows polling, cycle problems and handler errors. Logs never contain pasted keys; a handler error logs only its exception type.
- `docker compose ps` should show the service `Up`. The service restarts itself (`restart: unless-stopped`) and the search resumes automatically if it was active.

**Update**
1. `git pull`
2. `docker compose up -d --build` (the data volume is kept; new tables are created on start).
3. Send `/status` in the chat to confirm the search is still active.

**Back up and restore** (the volume holds the database, profile, settings and generated files)
- Find the volume name: `docker volume ls` (it ends in `jh-data`).
- Back up: `docker run --rm -v <volume>:/data -v "$PWD":/backup alpine tar czf /backup/jh-data.tgz -C /data .`
- Restore: stop the service (`docker compose down`), then `docker run --rm -v <volume>:/data -v "$PWD":/backup alpine sh -c "cd /data && tar xzf /backup/jh-data.tgz"`, then start it again.
- Back up `.env` separately and keep it private. A restored database is only readable with the same `JH_MASTER_KEY`.

**Rotate or lose the master key**
1. Stop the bot: `docker compose down`.
2. Put a new `JH_MASTER_KEY` in `.env`.
3. Delete the stored keys (they cannot be decrypted any more):
   `docker compose run --rm jobharness python -c "import sqlite3; c = sqlite3.connect('/data/jobharness.db'); c.execute('delete from secrets'); c.commit()"`
4. `docker compose up -d`, then reconnect each provider in the chat.

**Rotate the Telegram token:** create a new token with @BotFather (its /revoke command), update `.env`, `docker compose up -d`.

**Change the daily token budget or defaults:** edit `config/config.yaml` (`llm.daily_token_budget`, `bot.*`), then rebuild. Personal choices from the chat live in the data volume and override this file.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| The bot never answers | Wrong token, or `TELEGRAM_OWNER_ID` is not your id (other users are ignored silently) | Check `jh doctor`, the logs, and your id via @userinfobot |
| Log says another instance is polling | Two copies of the bot use the same token | Stop the other copy (`docker compose ps`, other hosts) |
| `/run` lists missing items | Profile, models, key or source not set up | Follow the list it prints |
| `/connect` says the key was rejected | Typo, revoked key, or provider outage | Retry; for SuperJob confirm the application key in the SuperJob developer area |
| Cycle fails with a provider error | Model id invalid for your OpenRouter account, or the model does not support structured output | `/models` to review; choose another id; check openrouter.ai status |
| Resumes arrive as `.txt` | `typst` is missing in the container | Rebuild the image; `jh doctor` must show `typst` ok |
| Jobs are found but nothing is delivered | Daily delivery cap reached, or the quality checks failed | `/status` shows both; raise `bot.max_deliveries_per_day` or improve the profile |
| Many parse failures | Model too weak for the job text language | Pick a stronger parse model with `/models` |

## Live smoke test (MVP acceptance, plan step 6.3)

Do this once, with real keys. It costs a small amount of LLM spend.

1. Start the bot as above; `jh doctor` is clean.
2. In the chat: `/start`, then `/profile_start` with your real facts (true statements only; metrics need evidence).
3. `/preferences`.
4. `/connect openrouter` and paste the key. **Check:** your message disappears and the bot says it is connected.
5. `/models set parse <id>`, then the same for `classify`, `compose`, `judge`.
6. `/connect superjob` (paste the key) and/or `/feed_add <rss-url>`. **Check:** the sample items look like real job posts.
7. `/run`. **Check:** the first cycle summary appears; within a few minutes at least one job arrives with a link, a resume file and a cover letter, written only from your profile.
8. Read the resume and letter for any claim you did not provide. If you find one, stop with `/pause` and report it as a defect.
9. Press Applied or Skip on a job; **check:** the message updates and the job does not reappear.
10. `/status` reports a successful cycle. Record the models you chose and any defects found in `docs/plans/mvp.md` step 6.3.

## Safety reminders (from §2, non-negotiable)

- **Truthfulness.** Nothing appears on a resume or letter that is not derivable from your profile. Gate G1 blocks unsupported claims.
- **You apply.** The bot never contacts employers.
- **Platform terms.** Only add feeds whose terms allow automated reading; the SuperJob terms are not yet verified (`docs/SOURCES.md`).
- **Keys.** Pasted keys are deleted from the chat at once and stored encrypted; never share `JH_MASTER_KEY`.
