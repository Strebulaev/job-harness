# SOURCES — per-adapter ToS notes

One entry per ingest adapter. The implementing agent MUST fill in `tos_notes` and `allowed_actions` from the source's actual ToS before the adapter is wired in.

**O1 sign-off (2026-10-04):** 1–2 API/RSS adapters. M2-2 implements the three
built-in adapters (manual, rss, email_alerts) + **1 API/RSS adapter**
(We Work Remotely, via the generic RSS adapter — cleanest ToS on the
candidate list). A second adapter is NOT implemented per O1.

| Adapter | Access method | ToS summary | Rate limit | Allowed actions | Notes |
|---|---|---|---|---|---|
| `manual` | CLI: `jh job add --url … [--paste]` | n/a — user-initiated | n/a | fetch | No ToS concern; the Principal pastes the URL or JD text. |
| `rss` | Generic RSS/Atom feed list in `config/config.yaml` | Varies by feed; each feed's ToS is recorded in its own row below | Per-feed | fetch | Feed URLs are config-driven; adding a feed is a config change, not a code change. |
| `email_alerts` | Parse job-alert emails from an IMAP label | Varies by sender; each sender's ToS is recorded in its own row below | n/a (polling is local) | fetch | The Principal signs up for the alerts; the harness only reads the label. Read-only IMAP; no sending. |
| `superjob` *(UNVERIFIED, plan 3.2)* | REST: `GET https://api.superjob.ru/2.0/vacancies/` with the application secret key in the `X-Api-App-Id` header | **Not confirmed**: official docs were behind a captcha when this was written. Principal must read the terms (storage, caching, attribution) before the live smoke test. | Unknown; the adapter self-limits to 1 request/second and 100 results per page | fetch | Shape taken from public client code and memory; see fact `superjob-api-shape-unverified`. Key is supplied by the bot (`/providers`), stored encrypted. |
| `weworkremotely` *(API-1, O1)* | RSS: `https://weworkremotely.com/remote-jobs.rss` | WWR publishes a public RSS feed of all current remote jobs. No ToS prohibition on programmatic reads of the feed; identify via User-Agent. | Be polite: cache with ETag/If-Modified-Since; no more than 1 request/min per feed. | fetch | Config-driven via `ingest.rss_feeds`. No API key, no CAPTCHA, no login. |

## Feed / sender sub-rows (fill as feeds are added)

| Feed / sender | URL or mailbox label | ToS summary | Rate limit | Allowed actions |
|---|---|---|---|---|
| We Work Remotely | `https://weworkremotely.com/remote-jobs.rss` | Public RSS feed; no ToS prohibition on programmatic reads. Identify via User-Agent. | 1 req/min; ETag/If-Modified-Since caching. | fetch |
| *(Remote OK)* | `https://remoteok.com/api` (if used) | Remote OK publishes a public JSON API. No ToS prohibition on programmatic reads; identify via User-Agent. | 100 req/day; ETag caching. | fetch |
| *(Habr Career)* | IMAP label: `habr-career` | Habr Career sends job-alert emails to subscribers. Read-only IMAP; no sending. | n/a (local polling). | fetch |
| *(djinni)* | IMAP label: `djinni-alerts` | djinni sends job-alert emails to subscribers. Read-only IMAP; no sending. | n/a (local polling). | fetch |

## Rules (from spec §11.1, §2.4)

- Each adapter declares `tos_notes` and `allowed_actions` in code (the `SourceAdapter` protocol, §11.1).
- Rate limiting per adapter; `User-Agent` identifies the tool; honor `robots.txt`; cache with ETag/If-Modified-Since.
- **No CAPTCHA bypass, no fingerprint evasion, no fake accounts, no bulk automated form submission** on platforms that prohibit it (§2.4). If a source's ToS forbids programmatic access, implement it as `email_alerts` or `manual` instead of an API adapter.
- Dedup: `url_hash` (canonicalized URL) and `jd_raw_hash`; fuzzy duplicate detection (company+title+similarity ≥ 0.92) links duplicates to the first job.
