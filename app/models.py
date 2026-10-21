from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role in ('business', 'participant', 'admin')", name="ck_users_role"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="participant")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AuthActionToken(Base):
    """Hashed, purpose-bound, one-time tokens for email verification and recovery."""

    __tablename__ = "auth_action_tokens"
    __table_args__ = (
        CheckConstraint("purpose in ('verify_email', 'reset_password')", name="ck_auth_action_token_purpose"),
        Index("ix_auth_action_tokens_user_purpose_created", "user_id", "purpose", "created_at"),
        Index("ix_auth_action_tokens_expires_at", "expires_at"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)


class DataSubjectRequest(Base):
    """Tracked intake record for a person's privacy-rights request."""

    __tablename__ = "data_subject_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type in ('access', 'correction', 'deletion', 'objection', 'other')",
            name="ck_data_subject_request_type",
        ),
        CheckConstraint(
            "status in ('open', 'in_review', 'needs_information', 'completed', 'rejected')",
            name="ck_data_subject_request_status",
        ),
        Index("ix_data_subject_requests_user_created", "user_id", "created_at"),
        Index("ix_data_subject_requests_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    request_type: Mapped[str] = mapped_column(String(24), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    resolution_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    handled_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SurveyCampaign(Base):
    __tablename__ = "survey_campaigns"
    __table_args__ = (
        CheckConstraint("status in ('draft', 'published', 'paused', 'closed')", name="ck_campaign_status"),
        CheckConstraint("reward_per_response_dzd >= 0", name="ck_reward_nonnegative"),
        CheckConstraint("response_limit between 1 and 5000", name="ck_response_limit"),
        CheckConstraint("version_number >= 0", name="ck_version_number"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    objective: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), nullable=False, default="")
    reward_per_response_dzd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_version_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    draft_schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    hypotheses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SurveyVersion(Base):
    __tablename__ = "survey_versions"
    __table_args__ = (UniqueConstraint("survey_id", "version_number", name="uq_survey_version_number"),)

    version_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("survey_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    hypotheses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SurveyResponse(Base):
    __tablename__ = "survey_responses"
    __table_args__ = (
        UniqueConstraint("survey_id", "submission_id", name="uq_survey_submission_idempotency"),
        Index("ix_response_survey_version_status", "survey_id", "survey_version_id", "status"),
        Index("ix_response_survey_participant", "survey_id", "participant_id"),
        CheckConstraint(
            "status in ('accepted', 'accepted_flagged', 'hold', 'screened_out', 'invalid', 'quota_full', 'excluded_duplicate')",
            name="ck_response_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("survey_campaigns.id", ondelete="CASCADE"), nullable=False)
    survey_version_id: Mapped[str] = mapped_column(ForeignKey("survey_versions.version_id", ondelete="RESTRICT"), nullable=False)
    submission_id: Mapped[str] = mapped_column(String(100), nullable=False)
    participant_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    answers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    signals_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    review_groups_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    errors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    pseudonym: Mapped[str] = mapped_column(String(64), nullable=False)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ResponseReview(Base):
    """One final human decision for a response held by automatic quality signals."""

    __tablename__ = "response_reviews"
    __table_args__ = (
        UniqueConstraint("response_id", name="uq_response_review_response"),
        CheckConstraint("decision in ('accept', 'reject')", name="ck_response_review_decision"),
        CheckConstraint(
            "reason_code in ('valid_response', 'ineligible', 'unusable_response', 'confirmed_duplicate', 'policy_violation', 'other')",
            name="ck_response_review_reason",
        ),
        Index("ix_response_reviews_reviewer_created", "reviewer_user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    response_id: Mapped[str] = mapped_column(ForeignKey("survey_responses.id", ondelete="CASCADE"), nullable=False)
    reviewer_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class RewardLedgerEntry(Base):
    __tablename__ = "reward_ledger"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_reward_ledger_idempotency"),
        CheckConstraint("amount_dzd > 0", name="ck_ledger_amount_positive"),
        Index("ix_reward_ledger_survey", "survey_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("survey_campaigns.id", ondelete="CASCADE"), nullable=False)
    response_id: Mapped[str | None] = mapped_column(ForeignKey("survey_responses.id", ondelete="RESTRICT"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    amount_dzd: Mapped[int] = mapped_column(Integer, nullable=False)
    available_delta_dzd: Mapped[int] = mapped_column(Integer, nullable=False)
    obligated_delta_dzd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paid_delta_dzd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reference: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class RewardObligation(Base):
    __tablename__ = "reward_obligations"
    __table_args__ = (
        UniqueConstraint("response_id", name="uq_reward_per_response"),
        CheckConstraint("amount_dzd > 0", name="ck_obligation_amount_positive"),
        CheckConstraint("status in ('pending', 'paid', 'cancelled')", name="ck_obligation_status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("survey_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    response_id: Mapped[str] = mapped_column(ForeignKey("survey_responses.id", ondelete="RESTRICT"), nullable=False)
    participant_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount_dzd: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    payment_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_target", "target_type", "target_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
