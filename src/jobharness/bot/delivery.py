"""Delivery of ready jobs to the Principal's chat (plan step 5.2).

Per job: one message (title, company, score, flags, link) with Applied/Skip
buttons, the resume (PDF, or text file when no PDF could be rendered) and the
cover letter text. Nothing here ever sends anything to an employer.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select

from jobharness.bot.core import BotCore, Ctx
from jobharness.bot.messenger import Button, Messenger
from jobharness.bot.user_settings import Runtime
from jobharness.db.models import Delivery, Document, Job
from jobharness.db.session import get_session
from jobharness.pipeline.stages import move
from jobharness.render.typst_renderer import resume_to_text
from jobharness.schemas.documents import CoverLetter, ResumeContent

MAX_TEXT = 3500


def _flags(job: Job) -> list[str]:
    reasons = json.loads(job.reject_reasons_json or "[]")
    return [r.removeprefix("flag:") for r in reasons if str(r).startswith("flag:")]


def _score_line(job: Job) -> str:
    parts = json.loads(job.score_breakdown_json or "{}")
    top = sorted(((k, v) for k, v in parts.items() if isinstance(v, (int, float))),
                 key=lambda kv: -kv[1])[:3]
    return ", ".join(f"{k} {v:g}" for k, v in top)


def job_message(job: Job) -> str:
    lines = [f"{job.title or 'Job'} — {job.company or 'unknown company'}"]
    if job.score is not None:
        lines.append(f"Match: {job.score:.0f}/100 · profile type: {job.archetype or '-'}")
    why = _score_line(job)
    if why:
        lines.append(f"Strongest: {why}")
    flags = _flags(job)
    if flags:
        lines.append("Check: " + ", ".join(flags))
    lines.append(f"Link: {job.url}")
    return "\n".join(lines)


def cover_message(letter: CoverLetter, name: str) -> str:
    return f"Dear Hiring Team,\n\n{letter.text}\n\nBest regards,\n{name}"


def delivered_today(now: datetime) -> int:
    with get_session()() as s:
        return int(s.execute(
            select(func.count()).select_from(Delivery).where(
                Delivery.delivered_at.like(f"{now.date().isoformat()}%")
            )
        ).scalar_one())


def _resume_file(rt: Runtime, job_id: int, doc: Document) -> Path:
    if doc.pdf_path and Path(doc.pdf_path).exists():
        return Path(doc.pdf_path)
    out = Path(rt.settings.paths.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    txt = out / f"job{job_id}.txt"
    if not txt.exists():
        txt.write_text(resume_to_text(ResumeContent.model_validate_json(doc.content_json or "{}")),
                       encoding="utf-8")
    return txt


async def deliver_ready(rt: Runtime, messenger: Messenger, chat_id: int, now: datetime) -> int:
    """Deliver queued jobs up to the daily cap. Returns how many were delivered."""
    cap = rt.settings.bot.max_deliveries_per_day - delivered_today(now)
    if cap <= 0:
        return 0
    with get_session()() as s:
        ids = list(s.execute(
            select(Job.id).where(Job.status == "queued").order_by(Job.score.desc(), Job.id).limit(cap)
        ).scalars().all())
    sent = 0
    for jid in ids:
        with get_session()() as s:
            job = s.get(Job, jid)
            assert job is not None
            docs = {d.kind: d for d in s.execute(
                select(Document).where(Document.job_id == jid).order_by(Document.id.desc())
            ).scalars().all()}
            text = job_message(job)
            resume_doc, cover_doc = docs.get("resume"), docs.get("cover")
            if resume_doc is None or cover_doc is None:
                continue
            letter = CoverLetter.model_validate_json(cover_doc.content_json or "{}")
            file_path = _resume_file(rt, jid, resume_doc)
        buttons = [[Button("Applied", f"dlv:applied:{jid}"), Button("Skip", f"dlv:skip:{jid}")]]
        try:
            mid = await messenger.send_text(chat_id, text, buttons)
            await messenger.send_document(chat_id, file_path, "Resume")
            body = cover_message(letter, rt.profile.identity.public_alias or rt.profile.identity.full_name)
            if len(body) > MAX_TEXT:
                cover_file = file_path.with_name(f"job{jid}_cover.txt")
                cover_file.write_text(body, encoding="utf-8")
                await messenger.send_document(chat_id, cover_file, "Cover letter")
            else:
                await messenger.send_text(chat_id, "Cover letter:\n\n" + body)
        except Exception:
            continue  # stays queued; retried next cycle
        with get_session()() as s:
            s.add(Delivery(job_id=jid, chat_message_id=mid, delivered_at=now.isoformat()))
            s.commit()
        move(jid, "delivered")
        sent += 1
    return sent


def register_delivery(core: BotCore) -> None:
    @core.callback("dlv")
    async def on_outcome(ctx: Ctx, data: str) -> None:
        _, outcome, raw_id = data.split(":")
        jid = int(raw_id)
        target = "applied" if outcome == "applied" else "skipped"
        with get_session()() as s:
            job = s.get(Job, jid)
            if job is None or job.status != "delivered":
                await ctx.reply("That job was already handled.")
                return
            title = job.title or "Job"
            row = s.execute(select(Delivery).where(Delivery.job_id == jid)).scalars().first()
            if row is not None:
                row.outcome = target
            s.commit()
            mid = row.chat_message_id if row else None
        move(jid, target)
        if mid is not None:
            await ctx.messenger.edit_text(ctx.chat_id, mid, f"{title} — marked as {target}.")
        else:
            await ctx.reply(f"Marked as {target}.")


__all__ = ["deliver_ready", "delivered_today", "job_message", "register_delivery"]
