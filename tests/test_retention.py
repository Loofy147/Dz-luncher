from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.db import initialize_schema, make_engine, make_session_factory
from app.models import (
    AuditEvent,
    AuthActionToken,
    AuthRateLimitBucket,
    AuthSession,
    User,
)
from app.services import ServiceError
from app.retention import preview_expired_auth_state, purge_expired_auth_state


def _system(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SESSION_SECRET", "retention-test-session-secret-at-least-32-bytes")
    engine = make_engine(f"sqlite:///{tmp_path / 'retention.db'}")
    initialize_schema(engine)
    factory = make_session_factory(engine)
    now = 1_800_000_000
    with factory() as session, session.begin():
        session.add_all([
            User(
                id="a" * 32, email="retention-admin@example.dz",
                display_name="Admin", password_hash="unused", role="admin",
            ),
            User(
                id="b" * 32, email="retention-user@example.dz",
                display_name="User", password_hash="unused", role="participant",
            ),
        ])
        session.flush()
        session.add_all([
            AuthSession(
                token_hash="1" * 64, user_id="b" * 32, csrf_token="2" * 64,
                expires_at=now - 1,
            ),
            AuthSession(
                token_hash="3" * 64, user_id="b" * 32, csrf_token="4" * 64,
                expires_at=now + 3_600,
            ),
            AuthActionToken(
                token_hash="5" * 64, user_id="b" * 32, purpose="verify_email",
                expires_at=now - 1, created_at=now - 86_401,
            ),
            AuthActionToken(
                token_hash="6" * 64, user_id="b" * 32, purpose="reset_password",
                expires_at=now + 600, created_at=now,
            ),
            AuthRateLimitBucket(
                bucket_key="7" * 64, window_start=now - 100_000, hits=3,
                updated_at=now - 86_401,
            ),
            AuthRateLimitBucket(
                bucket_key="8" * 64, window_start=now, hits=1,
                updated_at=now,
            ),
        ])
    return engine, factory, now


def test_preview_counts_expired_artifacts_without_deleting_anything(tmp_path, monkeypatch):
    engine, factory, now = _system(tmp_path, monkeypatch)
    try:
        plan = preview_expired_auth_state(factory, now=now)
        assert plan == {
            "as_of_epoch": now,
            "expired_sessions": 1,
            "expired_action_tokens": 1,
            "stale_rate_limit_buckets": 1,
            "total_records": 3,
        }
        with factory() as session:
            assert len(list(session.scalars(select(AuthSession)))) == 2
            assert len(list(session.scalars(select(AuthActionToken)))) == 2
            assert len(list(session.scalars(select(AuthRateLimitBucket)))) == 2
    finally:
        engine.dispose()


def test_purge_removes_only_expired_auth_artifacts_and_writes_minimal_audit(tmp_path, monkeypatch):
    engine, factory, now = _system(tmp_path, monkeypatch)
    try:
        result = purge_expired_auth_state(
            factory, operator_user_id="a" * 32, now=now,
        )
        assert result["expired_sessions_deleted"] == 1
        assert result["expired_action_tokens_deleted"] == 1
        assert result["stale_rate_limit_buckets_deleted"] == 1
        assert result["total_records_deleted"] == 3
        with factory() as session:
            assert len(list(session.scalars(select(AuthSession)))) == 1
            assert len(list(session.scalars(select(AuthActionToken)))) == 1
            assert len(list(session.scalars(select(AuthRateLimitBucket)))) == 1
            audit = session.scalar(select(AuditEvent).where(
                AuditEvent.event_type == "retention.expired_auth_state_purged",
            ))
            assert audit is not None
            details = json.loads(audit.details_json)
            assert details["total_records_deleted"] == 3
            assert "retention-admin@example.dz" not in audit.details_json
            assert "7" * 64 not in audit.details_json
        repeated = purge_expired_auth_state(
            factory, operator_user_id="a" * 32, now=now,
        )
        assert repeated["total_records_deleted"] == 0
    finally:
        engine.dispose()


def test_purge_requires_admin_and_leaves_records_untouched_on_denial(tmp_path, monkeypatch):
    engine, factory, now = _system(tmp_path, monkeypatch)
    try:
        with pytest.raises(ServiceError) as caught:
            purge_expired_auth_state(factory, operator_user_id="b" * 32, now=now)
        assert caught.value.status_code == 403
        assert caught.value.code == "admin_required"
        with factory() as session:
            assert len(list(session.scalars(select(AuthSession)))) == 2
            assert len(list(session.scalars(select(AuthActionToken)))) == 2
            assert len(list(session.scalars(select(AuthRateLimitBucket)))) == 2
    finally:
        engine.dispose()
