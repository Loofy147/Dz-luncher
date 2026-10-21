from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import initialize_schema, make_engine, make_session_factory
from app.main import create_app


def test_login_attempts_are_throttled_with_retry_after(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SESSION_SECRET", "rate-limit-session-secret-with-at-least-32-bytes")
    monkeypatch.setenv("PSEUDONYM_SECRET", "rate-limit-pseudonym-secret-with-at-least-32-bytes")

    engine = make_engine(f"sqlite:///{tmp_path / 'auth-rate-limits.db'}")
    initialize_schema(engine)
    factory = make_session_factory(engine)
    app = create_app(engine=engine, session_factory=factory, initialize=False)

    try:
        with TestClient(app) as client:
            responses = [
                client.post(
                    "/login",
                    data={"email": "unknown@example.dz", "password": "not-the-right-password"},
                    follow_redirects=False,
                )
                for _ in range(11)
            ]

        assert [response.status_code for response in responses[:10]] == [401] * 10
        blocked = responses[10]
        assert blocked.status_code == 429
        assert 1 <= int(blocked.headers["Retry-After"]) <= 900
    finally:
        engine.dispose()
