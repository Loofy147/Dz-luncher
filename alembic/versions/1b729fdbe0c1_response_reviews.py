"""add human response review records

Revision ID: 1b729fdbe0c1
Revises: f3106b7a21c4
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "1b729fdbe0c1"
down_revision: Union[str, None] = "f3106b7a21c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "response_reviews",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("response_id", sa.String(length=32), nullable=False),
        sa.Column("reviewer_user_id", sa.String(length=32), nullable=True),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision in ('accept', 'reject')", name="ck_response_review_decision"),
        sa.CheckConstraint(
            "reason_code in ('valid_response', 'ineligible', 'unusable_response', 'confirmed_duplicate', 'policy_violation', 'other')",
            name="ck_response_review_reason",
        ),
        sa.ForeignKeyConstraint(["response_id"], ["survey_responses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("response_id", name="uq_response_review_response"),
    )
    op.create_index(
        "ix_response_reviews_reviewer_created",
        "response_reviews",
        ["reviewer_user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_response_reviews_reviewer_created", table_name="response_reviews")
    op.drop_table("response_reviews")
