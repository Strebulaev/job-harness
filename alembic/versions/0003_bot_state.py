"""Bot state and deliveries tables (plan steps 4.2, 5.2).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bot_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False, unique=True),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), index=True),
        sa.Column("chat_message_id", sa.Integer()),
        sa.Column("delivered_at", sa.String(32)),
        sa.Column("outcome", sa.String(16)),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )


def downgrade() -> None:
    op.drop_table("deliveries")
    op.drop_table("bot_state")
