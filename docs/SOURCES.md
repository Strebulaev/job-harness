# SOURCES — per-adapter ToS notes

One entry per ingest adapter. The implementing agent MUST fill in `tos_notes` and `allowed_actions` from the source's actual ToS before the adapter is wired in. The list below is a skeleton; the two API adapters are placeholders until O1/O2 are signed off (see `docs/DECISIONS.md`).

| Adapter | Access method | ToS summary (to be filled) | Rate limit (to be filled) | Allowed actions | Notes |
|---|---|---|---|---|---|
| `manual` | CLI: `jh job add --url … [--paste]` | n/a — user-initiated | n/a | fetch | No ToS concern; the Principal pastes the URL or JD text. |
| `rss` | Generic RSS/Atom feed list in `config/config.yaml` | Varies by feed; each feed's ToS is recorded in its own row below | Per-feed | fetch | Feed URLs are config-driven; adding a feed is a config change, not a code change. |
| `email_alerts` | Parse job-alert emails from an IMAP label | Varies by sender; each sender's ToS is recorded in its own row below | n/a (polling is local) | fetch | The Principal signs up for the alerts; the harness only reads the label. |
| **API-1** *(placeholder, O1)* | API or RSS | **to be confirmed by Principal** | to be filled | fetch only | Spec §20 M2 placeholder: 1–2 permitted API adapters. Candidate list from §11.1: Remote OK, We Work Remotely, Himalayas, Working Nomads, Wellfound alerts, Habr Career, djinni alerts. Pick the one with the cleanest ToS + rate limit. |
| **API-2** *(placeholder, O1)* | API or RSS | **to be confirmed by Principal** | to be filled | fetch only | Same candidate list; add only if O1 is overridden to "2–3" and a second source has clean ToS. |

## Feed / sender sub-rows (fill as feeds are added)

| Feed / sender | URL or mailbox label | ToS summary | Rate limit | Allowed actions |
|---|---|---|---|---|
| *(example: Remote OK)* | `https://remoteok.com/api` (if used) | to be filled | to be filled | fetch |
| *(example: We Work Remotely)* | `https://weworkremotely.com/remote-jobs.rss` | to be filled | to be filled | fetch |

## Rules (from spec §11.1, §2.4)

- Each adapter declares `tos_notes` and `allowed_actions` in code (the `SourceAdapter` protocol, §11.1).
- Rate limiting per adapter; `User-Agent` identifies the tool; honor `robots.txt`; cache with ETag/If-Modified-Since.
- **No CAPTCHA bypass, no fingerprint evasion, no fake accounts, no bulk automated form submission** on platforms that prohibit it (§2.4). If a source's ToS forbids programmatic access, implement it as `email_alerts` or `manual` instead of an API adapter.
- Dedup: `url_hash` (canonicalized URL) and `jd_raw_hash`; fuzzy duplicate detection (company+title+similarity ≥ 0.92) links duplicates to the first job.
