"""add participant appeal and second-level adjudication records

Revision ID: 9c5f31ba02d7
Revises: 1b729fdbe0c1
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9c5f31ba02d7"
down_revision: Union[str, None] = "1b729fdbe0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "response_appeals",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("response_id", sa.String(length=32), nullable=False),
        sa.Column("participant_id", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=False),
        sa.Column("handled_by_user_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('open', 'in_review', 'upheld', 'overturned')",
            name="ck_response_appeal_status",
        ),
        sa.ForeignKeyConstraint(["response_id"], ["survey_responses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["handled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("response_id", name="uq_response_appeal_response"),
    )
    op.create_index(
        "ix_response_appeals_status_created", "response_appeals", ["status", "created_at"], unique=False,
    )
    op.create_index(
        "ix_response_appeals_participant_created", "response_appeals", ["participant_id", "created_at"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_response_appeals_participant_created", table_name="response_appeals")
    op.drop_index("ix_response_appeals_status_created", table_name="response_appeals")
    op.drop_table("response_appeals")
