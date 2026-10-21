from __future__ import annotations

from sqlalchemy import select

from app.db import initialize_schema, make_engine, make_session_factory
from app.models import AuthRateLimitBucket
from app.rate_limits import consume_rate_limit


def _factory(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SESSION_SECRET", "rate-limit-test-secret-with-at-least-32-bytes")
    engine = make_engine(f"sqlite:///{tmp_path / 'rate-limit-unit.db'}")
    initialize_schema(engine)
    return engine, make_session_factory(engine)


def test_fixed_window_counter_allows_limit_then_blocks_and_resets(tmp_path, monkeypatch):
    engine, factory = _factory(tmp_path, monkeypatch)
    try:
        first = consume_rate_limit(factory, scope="auth:login", key_material="198.51.100.10",
                                   limit=2, window_seconds=60, now=121)
        second = consume_rate_limit(factory, scope="auth:login", key_material="198.51.100.10",
                                    limit=2, window_seconds=60, now=122)
        third = consume_rate_limit(factory, scope="auth:login", key_material="198.51.100.10",
                                   limit=2, window_seconds=60, now=123)

        assert first.allowed and first.attempts == 1
        assert second.allowed and second.attempts == 2
        assert not third.allowed and third.attempts == 3
        assert third.retry_after == 57

        next_window = consume_rate_limit(factory, scope="auth:login", key_material="198.51.100.10",
                                         limit=2, window_seconds=60, now=180)
        assert next_window.allowed and next_window.attempts == 1
    finally:
        engine.dispose()


def test_persisted_bucket_contains_no_raw_client_identifier(tmp_path, monkeypatch):
    engine, factory = _factory(tmp_path, monkeypatch)
    client_ip = "203.0.113.77"
    try:
        consume_rate_limit(factory, scope="auth:login", key_material=client_ip,
                           limit=10, window_seconds=900, now=1000)
        with factory() as session:
            rows = list(session.scalars(select(AuthRateLimitBucket)))
            assert len(rows) == 1
            assert len(rows[0].bucket_key) == 64
            assert client_ip not in rows[0].bucket_key
            assert rows[0].hits == 1
    finally:
        engine.dispose()


def test_rate_limit_scopes_are_independent(tmp_path, monkeypatch):
    engine, factory = _factory(tmp_path, monkeypatch)
    try:
        consume_rate_limit(factory, scope="auth:login", key_material="test-client",
                           limit=1, window_seconds=60, now=100)
        blocked_login = consume_rate_limit(factory, scope="auth:login", key_material="test-client",
                                           limit=1, window_seconds=60, now=101)
        separate_action = consume_rate_limit(factory, scope="auth:register", key_material="test-client",
                                              limit=1, window_seconds=60, now=101)
        assert not blocked_login.allowed
        assert separate_action.allowed and separate_action.attempts == 1
    finally:
        engine.dispose()


def test_rate_limit_rejects_invalid_policy_values(tmp_path, monkeypatch):
    engine, factory = _factory(tmp_path, monkeypatch)
    try:
        for kwargs in (
            {"limit": 0, "window_seconds": 60},
            {"limit": 2, "window_seconds": 0},
            {"limit": True, "window_seconds": 60},
        ):
            try:
                consume_rate_limit(factory, scope="auth:login", key_material="test-client",
                                   now=100, **kwargs)
            except ValueError:
                continue
            raise AssertionError(f"invalid rate-limit configuration was accepted: {kwargs}")
    finally:
        engine.dispose()
