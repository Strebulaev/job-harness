"""Encrypted secrets table (plan step 3.4).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secrets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.String(32)),
        sa.Column("updated_at", sa.String(32)),
    )


def downgrade() -> None:
    op.drop_table("secrets")
