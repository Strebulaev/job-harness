"""SQLAlchemy 2.x ORM models for the 11 tables in spec §6.

All tables have ``id`` (integer PK), ``created_at``, ``updated_at`` (UTC).
Indexes are on every foreign key and on ``jobs(status)``, ``jobs(score)``,
``events(application_id, ts)``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Shared declarative base with audit columns."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(
        String(32), default=lambda: utcnow().isoformat(), index=False
    )
    updated_at: Mapped[str] = mapped_column(
        String(32), default=lambda: utcnow().isoformat(), onupdate=lambda: utcnow().isoformat()
    )


class Source(Base):
    """``sources`` uses ``id`` as its PK (for ORM compatibility), with ``name``
    as a unique natural key (spec §6)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    kind: Mapped[str | None] = mapped_column(String(64))
    tos_notes: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[str | None] = mapped_column(String(32))


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_score", "score"),
    )

    source: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("sources.name"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(128))
    url: Mapped[str | None] = mapped_column(Text)
    url_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    company: Mapped[str | None] = mapped_column(String(256))
    title: Mapped[str | None] = mapped_column(String(512))
    jd_raw: Mapped[str | None] = mapped_column(Text)
    jd_raw_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    jd_parsed_json: Mapped[str | None] = mapped_column(Text)
    parse_model: Mapped[str | None] = mapped_column(String(128))
    parse_prompt_version: Mapped[str | None] = mapped_column(String(32))
    country: Mapped[str | None] = mapped_column(String(8))
    remote_policy: Mapped[str | None] = mapped_column(String(16))
    engagement_type: Mapped[str | None] = mapped_column(String(16))
    comp_min_usd_month: Mapped[float | None] = mapped_column(Float)
    comp_max_usd_month: Mapped[float | None] = mapped_column(Float)
    comp_confidence: Mapped[str | None] = mapped_column(String(16))
    overlap_hours: Mapped[float | None] = mapped_column(Float)
    ai_policy: Mapped[str | None] = mapped_column(String(16))
    subcontracting_policy: Mapped[str | None] = mapped_column(String(16))
    exclusivity: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column(Float)
    score_breakdown_json: Mapped[str | None] = mapped_column(Text)
    archetype: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="new")
    reject_reasons_json: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[str | None] = mapped_column(String(32))
    last_seen_at: Mapped[str | None] = mapped_column(String(32))


class Document(Base):
    __tablename__ = "documents"

    job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("jobs.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # resume | cover
    archetype: Mapped[str | None] = mapped_column(String(64))
    content_json: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    pdf_path: Mapped[str | None] = mapped_column(String(512))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    temperature: Mapped[float | None] = mapped_column(Float)
    inputs_hash: Mapped[str | None] = mapped_column(String(64))
    eval_json: Mapped[str | None] = mapped_column(Text)
    eval_pass: Mapped[bool | None] = mapped_column(Boolean)
    iteration: Mapped[int | None] = mapped_column(Integer, default=0)
    experiment_id: Mapped[str | None] = mapped_column(String(64))
    variant: Mapped[str | None] = mapped_column(String(64))


class Application(Base):
    __tablename__ = "applications"

    job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("jobs.id"), index=True
    )
    resume_doc_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("documents.id"), index=True
    )
    cover_doc_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("documents.id"), index=True
    )
    channel: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    approved_at: Mapped[str | None] = mapped_column(String(32))
    sent_at: Mapped[str | None] = mapped_column(String(32))
    proposed_rate_usd_month: Mapped[float | None] = mapped_column(Float)
    proposed_hours_week: Mapped[float | None] = mapped_column(Float)


class Contact(Base):
    __tablename__ = "contacts"

    company: Mapped[str | None] = mapped_column(String(256))
    name: Mapped[str | None] = mapped_column(String(256))
    role: Mapped[str | None] = mapped_column(String(256))
    email: Mapped[str | None] = mapped_column(String(256))
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Message(Base):
    __tablename__ = "messages"

    application_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("applications.id"), index=True
    )
    direction: Mapped[str] = mapped_column(String(4))  # in | out
    channel: Mapped[str | None] = mapped_column(String(32))
    message_id_header: Mapped[str | None] = mapped_column(String(512), unique=True)
    thread_id: Mapped[str | None] = mapped_column(String(256))
    from_addr: Mapped[str | None] = mapped_column(String(256))
    to_addr: Mapped[str | None] = mapped_column(String(256))
    subject: Mapped[str | None] = mapped_column(String(512))
    body_text: Mapped[str | None] = mapped_column(Text)
    received_or_sent_at: Mapped[str | None] = mapped_column(String(32))
    classification: Mapped[str | None] = mapped_column(String(32))
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    needs_human: Mapped[bool | None] = mapped_column(Boolean)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_app_ts", "application_id", "ts"),)

    application_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("applications.id"), index=True
    )
    type: Mapped[str] = mapped_column(String(32))
    ts: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[str | None] = mapped_column(Text)


class Followup(Base):
    __tablename__ = "followups"

    application_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("applications.id"), index=True
    )
    due_at: Mapped[str | None] = mapped_column(String(32))
    sequence: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(32))
    draft_doc_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("documents.id"), index=True
    )


class Contract(Base):
    __tablename__ = "contracts"

    application_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("applications.id"), index=True
    )
    company: Mapped[str | None] = mapped_column(String(256))
    rate_usd_month: Mapped[float | None] = mapped_column(Float)
    hours_week: Mapped[float | None] = mapped_column(Float)
    start_date: Mapped[str | None] = mapped_column(String(16))
    end_date: Mapped[str | None] = mapped_column(String(16))
    ai_tools_allowed: Mapped[str | None] = mapped_column(String(16))
    subcontracting_allowed: Mapped[str | None] = mapped_column(String(16))
    nda_scope: Mapped[str | None] = mapped_column(Text)
    exclusivity: Mapped[int | None] = mapped_column(Integer)
    ip_terms: Mapped[str | None] = mapped_column(Text)
    overlap_window_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int | None] = mapped_column(Integer)
    results_json: Mapped[str | None] = mapped_column(Text)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    git_sha: Mapped[str | None] = mapped_column(String(64))


class LLMCall(Base):
    __tablename__ = "llm_calls"

    purpose: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    request_hash: Mapped[str | None] = mapped_column(String(64))
    ok: Mapped[bool | None] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)


class Secret(Base):
    """Encrypted provider secrets (plan step 3.4). Never stores plaintext."""

    __tablename__ = "secrets"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class BotState(Base):
    """Key/value JSON state for the Telegram bot (plan step 4.2)."""

    __tablename__ = "bot_state"

    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)


class Delivery(Base):
    """One job delivered to the Principal's chat (plan step 5.2)."""

    __tablename__ = "deliveries"

    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), index=True)
    chat_message_id: Mapped[int | None] = mapped_column(Integer)
    delivered_at: Mapped[str | None] = mapped_column(String(32))
    outcome: Mapped[str | None] = mapped_column(String(16))  # applied | skipped


# Touch all models so Alembic autogenerate and `Base.metadata` see them.
__all__ = [
    "Base",
    "Source",
    "Job",
    "Document",
    "Application",
    "Contact",
    "Message",
    "Event",
    "Followup",
    "Contract",
    "EvalRun",
    "LLMCall",
    "Secret",
    "BotState",
    "Delivery",
]
