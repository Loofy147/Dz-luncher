"""add persistent authentication rate-limit buckets

Revision ID: d0f4e783a219
Revises: bc9f6a7102dd
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d0f4e783a219"
down_revision: Union[str, None] = "bc9f6a7102dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limit_buckets",
        sa.Column("bucket_key", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("hits >= 1", name="ck_auth_rate_limit_hits_positive"),
        sa.PrimaryKeyConstraint("bucket_key"),
    )
    op.create_index(
        "ix_auth_rate_limit_buckets_updated_at",
        "auth_rate_limit_buckets",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_auth_rate_limit_buckets_updated_at", table_name="auth_rate_limit_buckets")
    op.drop_table("auth_rate_limit_buckets")
