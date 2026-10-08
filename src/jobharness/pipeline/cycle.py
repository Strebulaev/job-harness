"""One search cycle: ingest -> parse -> route -> compose -> render -> gate (plan step 5.1).

Idempotent: every stage selects jobs by status, so a crash resumes without
duplicates. One failing job never aborts the cycle. LLM stages stop when the
daily token budget is reached.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy import func, select

from jobharness.bot.user_settings import Runtime, profile_path
from jobharness.db.models import Document, Job, LLMCall, Source
from jobharness.db.session import get_session
from jobharness.eval.runner import Models, compose_gated, record_eval_run
from jobharness.ingest.base import RawJob
from jobharness.ingest.dedup import Deduper
from jobharness.ingest.rss import RssAdapter
from jobharness.ingest.superjob import SuperJobAdapter, build_superjob_queries
from jobharness.llm.prompt_versions import default_version
from jobharness.llm.provider import LLMProvider
from jobharness.pipeline.stages import move, parse_job, route_one
from jobharness.render.typst_renderer import (
    RenderError,
    render_resume,
    resume_to_text,
    typst_available,
)
from jobharness.schemas.documents import ResumeContent
from jobharness.schemas.jd import JDParsed

_log = logging.getLogger(__name__)
SUPERJOB_SECRET = "superjob_api_key"
PARSE_CONCURRENCY = 4


@dataclass
class CycleReport:
    fetched: int = 0
    inserted: int = 0
    parsed: int = 0
    parse_failed: int = 0
    rejected: int = 0
    shortlisted: int = 0
    composed_ok: int = 0
    gated_fail: int = 0
    skipped_budget: int = 0
    errors: list[str] = field(default_factory=list)
    refused: str | None = None
    started_at: str = ""
    finished_at: str = ""

    def as_dict(self) -> dict[str, object]:
        return dict(self.__dict__)


@dataclass
class CycleDeps:
    runtime: Runtime
    provider: LLMProvider
    superjob_key: Callable[[], str | None]
    now: datetime
    transport: httpx.AsyncBaseTransport | None = None


def tokens_used_today(now: datetime) -> int:
    day = now.date().isoformat()
    with get_session()() as s:
        total = s.execute(
            select(func.coalesce(func.sum(LLMCall.input_tokens + LLMCall.output_tokens), 0)).where(
                LLMCall.created_at.like(f"{day}%")
            )
        ).scalar_one()
    return int(total)


def _ensure_sources(names: list[tuple[str, str, str]]) -> None:
    with get_session()() as s:
        for name, kind, tos in names:
            if s.execute(select(Source).where(Source.name == name)).scalar_one_or_none() is None:
                s.add(Source(name=name, kind=kind, tos_notes=tos, enabled=True))
        s.commit()


async def _ingest(deps: CycleDeps, report: CycleReport) -> None:
    rt = deps.runtime
    _ensure_sources([
        ("superjob", "api", "UNVERIFIED terms; see docs/SOURCES.md"),
        ("rss", "rss", "user-attested feeds"),
    ])
    raws: list[RawJob] = []
    if deps.superjob_key():
        queries = build_superjob_queries(rt.profile)
        sj = SuperJobAdapter(
            deps.superjob_key, queries,
            user_agent=rt.settings.ingest.user_agent if rt.settings.ingest else "jobharness/0.1",
            transport=deps.transport,
        )
        try:
            raws += [r async for r in sj.fetch()]
        except Exception as e:
            report.errors.append(f"superjob: {type(e).__name__}: {str(e)[:120]}")
    feeds = rt.settings.ingest.rss_feeds if rt.settings.ingest else []
    if feeds:
        rss = RssAdapter(
            feeds,
            user_agent=rt.settings.ingest.user_agent if rt.settings.ingest else "jobharness/0.1",
            transport=deps.transport,
        )
        try:
            raws += [r async for r in rss.fetch()]
        except Exception as e:
            report.errors.append(f"rss: {type(e).__name__}: {str(e)[:120]}")
    report.fetched = len(raws)
    if not raws:
        return
    with get_session()() as s:
        deduper = Deduper(s)
        result = deduper.check_batch(raws)
        for r in result.results:
            if r.action == "insert":
                deduper.insert_job(r.raw, url_hash_=r.url_hash, jd_hash_=r.jd_hash)
                report.inserted += 1
        s.commit()


def _job_ids(status: str, limit: int) -> list[int]:
    with get_session()() as s:
        return list(
            s.execute(select(Job.id).where(Job.status == status).order_by(Job.id).limit(limit))
            .scalars()
            .all()
        )


def _make_render(out_dir: Path) -> Callable[[ResumeContent, str], Path | None]:
    def render(content: ResumeContent, stem: str) -> Path | None:
        if typst_available():
            try:
                return render_resume(content, out_dir, stem).pdf
            except RenderError as e:
                _log.warning("render failed, falling back to text: %s", e)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{stem}.txt").write_text(resume_to_text(content), encoding="utf-8")
        return None

    return render


async def run_cycle(deps: CycleDeps) -> CycleReport:
    rt = deps.runtime
    report = CycleReport(started_at=deps.now.isoformat())
    cfg = rt.settings
    budget = cfg.llm.daily_token_budget
    max_jobs = cfg.bot.max_jobs_per_cycle

    sources_ready = bool(deps.superjob_key()) or bool(cfg.ingest and cfg.ingest.rss_feeds)
    if not sources_ready:
        report.refused = "no sources: connect SuperJob or add an RSS feed"
        return report
    if not rt.profile.experience or not rt.profile.skills:
        report.refused = "profile needs at least one role and some skills"
        return report

    await _ingest(deps, report)

    # ---- parse
    new_ids = _job_ids("new", max_jobs)
    sem = asyncio.Semaphore(PARSE_CONCURRENCY)

    async def parse_bounded(jid: int) -> tuple[int, bool, str]:
        async with sem:
            if tokens_used_today(deps.now) >= budget:
                return jid, False, "budget"
            try:
                ok, detail = await parse_job(jid, deps.provider, cfg)
            except Exception as e:  # never abort the cycle for one job
                return jid, False, f"{type(e).__name__}: {str(e)[:100]}"
            return jid, ok, detail

    for jid, ok, detail in await asyncio.gather(*(parse_bounded(j) for j in new_ids)):
        if detail == "budget":
            report.skipped_budget += 1
        elif ok:
            report.parsed += 1
        else:
            report.parse_failed += 1
            report.errors.append(f"job {jid}: {detail}")

    # ---- route
    for jid in _job_ids("parsed", max_jobs * 3):
        try:
            status = route_one(jid, rt.profile, rt.positioning, rt.archetypes, cfg)
        except Exception as e:
            report.errors.append(f"route job {jid}: {type(e).__name__}: {str(e)[:100]}")
            continue
        if status == "shortlisted":
            report.shortlisted += 1
        else:
            report.rejected += 1

    # ---- compose, render, gate
    models = Models(compose=cfg.llm.models.compose, judge=cfg.llm.models.judge)
    render = _make_render(Path(cfg.paths.output_dir))
    profile_hash = hashlib.sha256(profile_path(rt.data_dir).read_bytes()).hexdigest()
    for jid in _job_ids("shortlisted", max_jobs):
        if tokens_used_today(deps.now) >= budget:
            report.skipped_budget += 1
            continue
        try:
            outcome = await _compose_one(jid, deps, models, render, profile_hash)
        except Exception as e:
            report.errors.append(f"compose job {jid}: {type(e).__name__}: {str(e)[:100]}")
            continue
        if outcome == "ok":
            report.composed_ok += 1
        else:
            report.gated_fail += 1

    report.finished_at = deps.now.isoformat()
    return report


async def _compose_one(
    jid: int,
    deps: CycleDeps,
    models: Models,
    render: Callable[[ResumeContent, str], Path | None],
    profile_hash: str,
) -> str:
    rt = deps.runtime
    with get_session()() as s:
        job = s.get(Job, jid)
        assert job is not None
        jd = JDParsed.model_validate_json(job.jd_parsed_json or "{}")
        archetype = rt.archetypes.get(job.archetype or "") or next(iter(rt.archetypes.values()))
        company, jd_hash = job.company, job.jd_raw_hash or ""
        flags = json.loads(job.reject_reasons_json or "[]")
    overqualified = "flag:overqualification_handson_focus" in flags
    stem = f"job{jid}"

    result = await compose_gated(
        rt.profile, archetype, rt.positioning, jd, deps.provider, models,
        today=deps.now.date(), company=company, overqualified=overqualified,
        render=lambda content: render(content, stem),
    )
    pdf = result.pdf_path
    inputs_hash = hashlib.sha256(
        json.dumps([jd_hash, profile_hash, models.compose, default_version("resume_compose")]).encode()
    ).hexdigest()
    eval_json = json.dumps(result.report.as_dict(), sort_keys=True)
    with get_session()() as s:
        resume_doc: Document | None = None
        for kind, payload in (
            ("resume", result.resume.content.model_dump_json()),
            ("cover", result.cover.letter.model_dump_json()),
        ):
            doc = Document(
                job_id=jid, kind=kind, archetype=archetype.id, content_json=payload,
                content_hash=hashlib.sha256(payload.encode()).hexdigest(),
                pdf_path=str(pdf) if (kind == "resume" and pdf) else None,
                prompt_version=default_version(f"{kind}_compose"), model=models.compose,
                temperature=rt.settings.llm.temperature.compose, inputs_hash=inputs_hash,
                eval_json=eval_json, eval_pass=result.report.passed,
                iteration=result.iterations - 1,
            )
            s.add(doc)
            if kind == "resume":
                resume_doc = doc
        s.flush()
        record_eval_run(
            s, "doc", resume_doc.id if resume_doc else jid, result.report.as_dict(),
            result.report.passed,
        )
        s.commit()
    if result.status == "ok":
        move(jid, "composed", "queued")
        return "ok"
    move(jid, "composed", "gated_fail")
    return "gated_fail"


__all__ = ["CycleDeps", "CycleReport", "run_cycle", "tokens_used_today"]
