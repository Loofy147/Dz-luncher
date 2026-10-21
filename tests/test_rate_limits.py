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



def test_forwarded_ip_header_is_ignored_unless_immediate_peer_is_trusted(tmp_path, monkeypatch):
    from starlette.requests import Request
    from app.rate_limits import _client_key

    monkeypatch.setenv("RATE_LIMIT_TRUSTED_CLIENT_IP_HEADER", "x-real-ip")
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    untrusted_peer = Request({
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "path": "/login",
        "query_string": b"",
        "headers": [(b"x-real-ip", b"198.51.100.99")],
        "client": ("203.0.113.7", 50000),
        "server": ("testserver", 80),
    })
    assert _client_key(untrusted_peer) == "203.0.113.7"


def test_forwarded_ip_header_is_used_for_configured_trusted_proxy(tmp_path, monkeypatch):
    from starlette.requests import Request
    from app.rate_limits import _client_key

    monkeypatch.setenv("RATE_LIMIT_TRUSTED_CLIENT_IP_HEADER", "x-real-ip")
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8,192.0.2.0/24")
    trusted_peer = Request({
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "path": "/login",
        "query_string": b"",
        "headers": [(b"x-real-ip", b"198.51.100.99")],
        "client": ("10.12.0.4", 50000),
        "server": ("testserver", 80),
    })
    assert _client_key(trusted_peer) == "198.51.100.99"


def test_concurrent_sqlite_attempts_never_admit_more_than_limit(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    engine, factory = _factory(tmp_path, monkeypatch)
    try:
        def hit(_):
            return consume_rate_limit(
                factory,
                scope="auth:concurrent",
                key_material="one-client",
                limit=5,
                window_seconds=60,
                now=120,
            )
        with ThreadPoolExecutor(max_workers=8) as pool:
            decisions = list(pool.map(hit, range(32)))
        assert sum(decision.allowed for decision in decisions) == 5
        assert max(decision.attempts for decision in decisions) == 32
    finally:
        engine.dispose()
