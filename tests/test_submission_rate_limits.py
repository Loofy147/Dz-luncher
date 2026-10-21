from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import initialize_schema, make_engine, make_session_factory
from app.main import create_app
from app.security import SESSION_COOKIE, create_session
from app.services import register_user


def _app(tmp_path, monkeypatch, filename: str):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SESSION_SECRET", "submission-rate-limit-secret-at-least-32-bytes")
    monkeypatch.setenv("PSEUDONYM_SECRET", "submission-rate-limit-pseudonym-secret-at-least-32-bytes")
    engine = make_engine(f"sqlite:///{tmp_path / filename}")
    initialize_schema(engine)
    factory = make_session_factory(engine)
    return engine, factory, create_app(engine=engine, session_factory=factory, initialize=False)


def test_submission_attempts_from_one_client_are_limited_before_authentication(tmp_path, monkeypatch):
    engine, _factory, app = _app(tmp_path, monkeypatch, "submission-ip-limit.db")
    try:
        with TestClient(app) as client:
            responses = [
                client.post("/api/surveys/nonexistent/responses", json={})
                for _ in range(61)
            ]

        assert all(response.status_code == 401 for response in responses[:60])
        blocked = responses[60]
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "rate_limit_exceeded"
        assert 1 <= int(blocked.headers["Retry-After"]) <= 3600
    finally:
        engine.dispose()


def test_submission_attempts_are_limited_per_participant_and_campaign(tmp_path, monkeypatch):
    engine, factory, app = _app(tmp_path, monkeypatch, "submission-participant-limit.db")
    try:
        user = register_user(
            factory,
            email="participant-rate-limit@example.dz",
            password="correct-horse-battery",
            display_name="مشارك اختبار",
            role="participant",
        )
        signed_session, csrf_token = create_session(factory, user)
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE, signed_session)
            assert client.get("/api/me").status_code == 200
            responses = [
                client.post(
                    "/api/surveys/nonexistent/responses",
                    json={},
                    headers={"X-CSRF-Token": csrf_token},
                )
                for _ in range(11)
            ]

        assert all(response.status_code != 429 for response in responses[:10])
        blocked = responses[10]
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "rate_limit_exceeded"
        assert 1 <= int(blocked.headers["Retry-After"]) <= 3600
    finally:
        engine.dispose()
