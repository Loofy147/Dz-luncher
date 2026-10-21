"""add tracked data-subject request workflow

Revision ID: f3106b7a21c4
Revises: 4e9bc271fa30
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f3106b7a21c4"
down_revision: Union[str, None] = "4e9bc271fa30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_subject_requests",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=True),
        sa.Column("request_type", sa.String(length=24), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=False),
        sa.Column("handled_by_user_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "request_type in ('access', 'correction', 'deletion', 'objection', 'other')",
            name="ck_data_subject_request_type",
        ),
        sa.CheckConstraint(
            "status in ('open', 'in_review', 'needs_information', 'completed', 'rejected')",
            name="ck_data_subject_request_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["handled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_data_subject_requests_user_created", "data_subject_requests", ["user_id", "created_at"], unique=False,
    )
    op.create_index(
        "ix_data_subject_requests_status_created", "data_subject_requests", ["status", "created_at"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_data_subject_requests_status_created", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_user_created", table_name="data_subject_requests")
    op.drop_table("data_subject_requests")
