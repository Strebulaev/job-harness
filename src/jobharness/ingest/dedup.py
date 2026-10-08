"""Dedup logic for ingested jobs (spec §11.1).

Three tiers:

1. **``url_hash``** — canonical URL SHA-256. Exact match → skip.
2. **``jd_raw_hash``** — whitespace-normalized JD text SHA-256. Exact
   match → link to the first job (the URL differs but the JD is the
   same, e.g. a repost or a syndicated listing).
3. **Fuzzy** — ``company + title`` similarity >= 0.92. Link the new job
   to the first matching job; the Principal can review.

The pipeline inserts a ``jobs`` row with ``status=new`` for every
non-duplicate :class:`~jobharness.ingest.base.RawJob`. Duplicates are
skipped (or linked) and reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jobharness.db.models import Job
from jobharness.ingest.base import RawJob
from jobharness.util.hashing import (
    company_title_key,
    fuzzy_similarity,
    jd_raw_hash,
    url_hash,
)

FUZZY_THRESHOLD = 0.92


@dataclass(slots=True)
class DedupResult:
    """Outcome of running one :class:`RawJob` through the dedup tiers."""

    raw: RawJob
    action: str  # "insert" | "url_dup" | "jd_dup" | "fuzzy_dup"
    matched_job_id: int | None = None
    url_hash: str = ""
    jd_hash: str = ""


@dataclass(slots=True)
class DedupReport:
    """Aggregate result of a dedup pass over a batch of RawJobs."""

    results: list[DedupResult] = field(default_factory=list)

    @property
    def inserted(self) -> list[DedupResult]:
        return [r for r in self.results if r.action == "insert"]

    @property
    def duplicates(self) -> list[DedupResult]:
        return [r for r in self.results if r.action != "insert"]

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {"insert": 0, "url_dup": 0, "jd_dup": 0, "fuzzy_dup": 0}
        for r in self.results:
            out[r.action] += 1
        return out


class Deduper:
    """Runs the three dedup tiers against a SQLAlchemy session.

    The deduper is stateless across calls; it queries the DB for
    existing ``jobs`` rows on each pass. The caller must commit the
    inserted rows.
    """

    def __init__(self, session: Any) -> None:
        self._s = session

    def check_batch(self, raw_jobs: list[RawJob]) -> DedupReport:
        """Run every RawJob through the three tiers.

        Returns a :class:`DedupReport` with one :class:`DedupResult` per
        input. The caller is responsible for inserting the ``insert``
        rows and committing.
        """
        report = DedupReport()
        # Index the existing jobs by url_hash, jd_raw_hash, and company+title.
        existing = list(self._s.query(Job).all())
        by_url: dict[str, Job] = {}
        by_jd: dict[str, Job] = {}
        by_ct: list[tuple[str, Job]] = []
        for j in existing:
            if j.url_hash:
                by_url[j.url_hash] = j
            if j.jd_raw_hash:
                by_jd[j.jd_raw_hash] = j
            if j.company or j.title:
                by_ct.append((company_title_key(j.company, j.title), j))

        # Also dedup within the batch itself.
        batch_url: dict[str, RawJob] = {}
        batch_jd: dict[str, RawJob] = {}
        batch_ct: list[tuple[str, RawJob]] = []

        for raw in raw_jobs:
            uh = url_hash(raw.url)
            jh = jd_raw_hash(raw.jd_text)
            ct_key = company_title_key(raw.company, raw.title)

            # Tier 1: url_hash
            matched: Job | None = by_url.get(uh)
            if matched is None and uh in batch_url:
                matched = None  # will be inserted later
            if matched is not None:
                report.results.append(
                    DedupResult(raw=raw, action="url_dup", matched_job_id=matched.id,
                                url_hash=uh, jd_hash=jh)
                )
                continue

            # Tier 2: jd_raw_hash
            matched = by_jd.get(jh)
            if matched is None and jh in batch_jd:
                matched = None
            if matched is not None:
                report.results.append(
                    DedupResult(raw=raw, action="jd_dup", matched_job_id=matched.id,
                                url_hash=uh, jd_hash=jh)
                )
                batch_url.setdefault(uh, raw)
                continue

            # Tier 3: fuzzy company+title
            fuzzy_match: Job | None = None
            for key, job in by_ct:
                if fuzzy_similarity(key, ct_key) >= FUZZY_THRESHOLD:
                    fuzzy_match = job
                    break
            if fuzzy_match is not None:
                report.results.append(
                    DedupResult(raw=raw, action="fuzzy_dup",
                                matched_job_id=fuzzy_match.id,
                                url_hash=uh, jd_hash=jh)
                )
                continue

            # No match: insert.
            report.results.append(
                DedupResult(raw=raw, action="insert", url_hash=uh, jd_hash=jh)
            )
            batch_url.setdefault(uh, raw)
            batch_jd.setdefault(jh, raw)
            batch_ct.append((ct_key, raw))

        return report

    def insert_job(self, raw: RawJob, *, url_hash_: str, jd_hash_: str) -> Job:
        """Insert a :class:`RawJob` as a ``jobs`` row with ``status=new``."""
        job = Job(
            source=raw.source,
            external_id=raw.external_id,
            url=raw.url,
            url_hash=url_hash_,
            title=raw.title,
            company=raw.company,
            jd_raw=raw.jd_text,
            jd_raw_hash=jd_hash_,
            status="new",
        )
        self._s.add(job)
        self._s.flush()
        return job


__all__ = [
    "FUZZY_THRESHOLD",
    "DedupReport",
    "DedupResult",
    "Deduper",
]
