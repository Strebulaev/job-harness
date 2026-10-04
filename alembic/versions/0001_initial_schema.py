"""Initial schema: 11 tables from spec §6.

Revision ID: 0001
Revises:
Create Date: 2026-10-03
"""

from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("name", sa.String(128), primary_key=True),
        sa.Column("kind", sa.String(64)),
        sa.Column("tos_notes", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default="1"),
        sa.Column("last_run_at", sa.String(32)),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(128), sa.ForeignKey("sources.name")),
        sa.Column("external_id", sa.String(128)),
        sa.Column("url", sa.Text()),
        sa.Column("url_hash", sa.String(64), unique=True),
        sa.Column("company", sa.String(256)),
        sa.Column("title", sa.String(512)),
        sa.Column("jd_raw", sa.Text()),
        sa.Column("jd_raw_hash", sa.String(64)),
        sa.Column("jd_parsed_json", sa.Text()),
        sa.Column("parse_model", sa.String(128)),
        sa.Column("parse_prompt_version", sa.String(32)),
        sa.Column("country", sa.String(8)),
        sa.Column("remote_policy", sa.String(16)),
        sa.Column("engagement_type", sa.String(16)),
        sa.Column("comp_min_usd_month", sa.REAL()),
        sa.Column("comp_max_usd_month", sa.REAL()),
        sa.Column("comp_confidence", sa.String(16)),
        sa.Column("overlap_hours", sa.REAL()),
        sa.Column("ai_policy", sa.String(16)),
        sa.Column("subcontracting_policy", sa.String(16)),
        sa.Column("exclusivity", sa.Integer()),
        sa.Column("score", sa.REAL()),
        sa.Column("score_breakdown_json", sa.Text()),
        sa.Column("archetype", sa.String(64)),
        sa.Column("status", sa.String(32), server_default="new"),
        sa.Column("reject_reasons_json", sa.Text()),
        sa.Column("first_seen_at", sa.String(32)),
        sa.Column("last_seen_at", sa.String(32)),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )
    op.create_index("ix_jobs_source", "jobs", ["source"])
    op.create_index("ix_jobs_url_hash", "jobs", ["url_hash"], unique=True)
    op.create_index("ix_jobs_jd_raw_hash", "jobs", ["jd_raw_hash"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_score", "jobs", ["score"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id")),
        sa.Column("kind", sa.String(16)),
        sa.Column("archetype", sa.String(64)),
        sa.Column("content_json", sa.Text()),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("pdf_path", sa.String(512)),
        sa.Column("prompt_version", sa.String(32)),
        sa.Column("model", sa.String(128)),
        sa.Column("temperature", sa.REAL()),
        sa.Column("inputs_hash", sa.String(64)),
        sa.Column("eval_json", sa.Text()),
        sa.Column("eval_pass", sa.Boolean()),
        sa.Column("iteration", sa.Integer(), server_default="0"),
        sa.Column("experiment_id", sa.String(64)),
        sa.Column("variant", sa.String(64)),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )
    op.create_index("ix_documents_job_id", "documents", ["job_id"])

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id")),
        sa.Column("resume_doc_id", sa.Integer(), sa.ForeignKey("documents.id")),
        sa.Column("cover_doc_id", sa.Integer(), sa.ForeignKey("documents.id")),
        sa.Column("channel", sa.String(32)),
        sa.Column("status", sa.String(32), server_default="queued"),
        sa.Column("approved_at", sa.String(32)),
        sa.Column("sent_at", sa.String(32)),
        sa.Column("proposed_rate_usd_month", sa.REAL()),
        sa.Column("proposed_hours_week", sa.REAL()),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_applications_resume_doc_id", "applications", ["resume_doc_id"])
    op.create_index("ix_applications_cover_doc_id", "applications", ["cover_doc_id"])

    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company", sa.String(256)),
        sa.Column("name", sa.String(256)),
        sa.Column("role", sa.String(256)),
        sa.Column("email", sa.String(256)),
        sa.Column("linkedin_url", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id")),
        sa.Column("direction", sa.String(4)),
        sa.Column("channel", sa.String(32)),
        sa.Column("message_id_header", sa.String(512), unique=True),
        sa.Column("thread_id", sa.String(256)),
        sa.Column("from_addr", sa.String(256)),
        sa.Column("to_addr", sa.String(256)),
        sa.Column("subject", sa.String(512)),
        sa.Column("body_text", sa.Text()),
        sa.Column("received_or_sent_at", sa.String(32)),
        sa.Column("classification", sa.String(32)),
        sa.Column("classification_confidence", sa.REAL()),
        sa.Column("needs_human", sa.Boolean()),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )
    op.create_index("ix_messages_application_id", "messages", ["application_id"])
    op.create_index(
        "ix_messages_message_id_header", "messages", ["message_id_header"], unique=True
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id")),
        sa.Column("type", sa.String(32)),
        sa.Column("ts", sa.String(32)),
        sa.Column("payload_json", sa.Text()),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )
    op.create_index("ix_events_application_id", "events", ["application_id"])
    op.create_index("ix_events_app_ts", "events", ["application_id", "ts"])

    op.create_table(
        "followups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id")),
        sa.Column("due_at", sa.String(32)),
        sa.Column("sequence", sa.Integer()),
        sa.Column("status", sa.String(32)),
        sa.Column("draft_doc_id", sa.Integer(), sa.ForeignKey("documents.id")),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )
    op.create_index("ix_followups_application_id", "followups", ["application_id"])
    op.create_index("ix_followups_draft_doc_id", "followups", ["draft_doc_id"])

    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id")),
        sa.Column("company", sa.String(256)),
        sa.Column("rate_usd_month", sa.REAL()),
        sa.Column("hours_week", sa.REAL()),
        sa.Column("start_date", sa.String(16)),
        sa.Column("end_date", sa.String(16)),
        sa.Column("ai_tools_allowed", sa.String(16)),
        sa.Column("subcontracting_allowed", sa.String(16)),
        sa.Column("nda_scope", sa.Text()),
        sa.Column("exclusivity", sa.Integer()),
        sa.Column("ip_terms", sa.Text()),
        sa.Column("overlap_window_json", sa.Text()),
        sa.Column("status", sa.String(16), server_default="active"),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )
    op.create_index("ix_contracts_application_id", "contracts", ["application_id"])

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(32)),
        sa.Column("target_id", sa.Integer()),
        sa.Column("results_json", sa.Text()),
        sa.Column("passed", sa.Boolean()),
        sa.Column("git_sha", sa.String(64)),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purpose", sa.String(64)),
        sa.Column("model", sa.String(128)),
        sa.Column("prompt_version", sa.String(32)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("cost_usd", sa.REAL()),
        sa.Column("request_hash", sa.String(64)),
        sa.Column("ok", sa.Boolean()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )


def downgrade() -> None:
    op.drop_table("llm_calls")
    op.drop_table("eval_runs")
    op.drop_table("contracts")
    op.drop_table("followups")
    op.drop_table("events")
    op.drop_table("messages")
    op.drop_table("contacts")
    op.drop_table("applications")
    op.drop_table("documents")
    op.drop_table("jobs")
    op.drop_table("sources")
