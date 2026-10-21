from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import initialize_schema, make_engine, make_session_factory
from app.main import create_app
from app.models import AuthActionToken, AuthSession, User


def _token_from_message(message: dict[str, str]) -> str:
    match = re.search(r"https?://[^\s]+", message["body"])
    assert match, message["body"]
    return parse_qs(urlsplit(match.group(0)).query)["token"][0]


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EMAIL_VERIFICATION_REQUIRED", "true")
    monkeypatch.setenv("SESSION_SECRET", "auth-flow-session-secret-with-at-least-32-bytes")
    monkeypatch.setenv("PSEUDONYM_SECRET", "auth-flow-pseudonym-secret-with-at-least-32-bytes")
    sent: list[dict[str, str]] = []

    def mailer(to_email: str, subject: str, body: str) -> None:
        sent.append({"to": to_email, "subject": subject, "body": body})

    engine = make_engine(f"sqlite:///{tmp_path / 'auth-flows.db'}")
    initialize_schema(engine)
    factory = make_session_factory(engine)
    application = create_app(engine=engine, session_factory=factory, initialize=False, mail_sender=mailer)
    return TestClient(application), engine, factory, sent


def test_registration_requires_verified_email_before_it_issues_a_session(tmp_path, monkeypatch):
    client, engine, factory, sent = _make_client(tmp_path, monkeypatch)
    try:
        response = client.post("/register", data={
            "display_name": "مشارك",
            "email": "participant@example.dz",
            "password": "correct-horse-battery",
            "role": "participant",
        }, follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/login?notice=verification_sent"
        assert "dz_session" not in response.cookies
        assert len(sent) == 1
        assert sent[0]["to"] == "participant@example.dz"
        assert "تأكيد البريد" in sent[0]["subject"]

        raw_token = _token_from_message(sent[0])
        token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
        with factory() as session:
            user = session.scalar(select(User).where(User.email == "participant@example.dz"))
            token_row = session.get(AuthActionToken, token_hash)
            assert user is not None and user.email_verified_at is None
            assert token_row is not None and token_row.purpose == "verify_email"
            assert token_row.token_hash != raw_token

        blocked = client.post("/login", data={
            "email": "participant@example.dz",
            "password": "correct-horse-battery",
        })
        assert blocked.status_code == 403

        confirmation = client.get("/verify-email", params={"token": raw_token})
        assert confirmation.status_code == 200
        assert "تأكيد البريد" in confirmation.text
        with factory() as session:
            assert session.get(AuthActionToken, token_hash) is not None  # GET must not consume a token.

        verified = client.post("/verify-email", data={"token": raw_token}, follow_redirects=False)
        assert verified.status_code == 303
        assert verified.headers["location"] == "/login?notice=email_verified"
        with factory() as session:
            user = session.scalar(select(User).where(User.email == "participant@example.dz"))
            assert user is not None and user.email_verified_at is not None
            assert session.get(AuthActionToken, token_hash) is None

        replay = client.post("/verify-email", data={"token": raw_token})
        assert replay.status_code in {400, 422}
        login = client.post("/login", data={
            "email": "participant@example.dz",
            "password": "correct-horse-battery",
        }, follow_redirects=False)
        assert login.status_code == 303
        assert "dz_session" in login.cookies
    finally:
        client.close()
        engine.dispose()


def test_password_reset_is_generic_single_use_and_revokes_all_existing_sessions(tmp_path, monkeypatch):
    client, engine, factory, sent = _make_client(tmp_path, monkeypatch)
    try:
        client.post("/register", data={
            "display_name": "صاحب مشروع",
            "email": "owner@example.dz",
            "password": "correct-horse-battery",
            "role": "business",
        }, follow_redirects=False)
        verify_token = _token_from_message(sent[-1])
        client.post("/verify-email", data={"token": verify_token})
        login = client.post("/login", data={
            "email": "owner@example.dz",
            "password": "correct-horse-battery",
        }, follow_redirects=False)
        assert login.status_code == 303
        assert client.get("/api/me").status_code == 200

        known = client.post("/forgot-password", data={"email": "owner@example.dz"}, follow_redirects=False)
        assert known.status_code == 303
        known_location = known.headers["location"]
        assert known_location == "/forgot-password?notice=if_account_exists"

        # Forget request for an unknown address is indistinguishable to the caller.
        sent_before_unknown = len(sent)
        unknown = client.post("/forgot-password", data={"email": "nobody@example.dz"}, follow_redirects=False)
        assert unknown.status_code == 303
        assert unknown.headers["location"] == known_location
        assert len(sent) == sent_before_unknown
        assert "إعادة تعيين كلمة المرور" in sent[-1]["subject"]

        reset_token = _token_from_message(sent[-1])
        token_hash = hashlib.sha256(reset_token.encode("ascii")).hexdigest()
        with factory() as session:
            token_row = session.get(AuthActionToken, token_hash)
            assert token_row is not None and token_row.purpose == "reset_password"
            assert token_row.token_hash != reset_token

        page = client.get("/reset-password", params={"token": reset_token})
        assert page.status_code == 200
        reset = client.post("/reset-password", data={
            "token": reset_token,
            "password": "new-correct-horse-battery",
            "password_confirm": "new-correct-horse-battery",
        }, follow_redirects=False)
        assert reset.status_code == 303
        assert reset.headers["location"] == "/login?notice=password_reset"
        assert client.get("/api/me").status_code == 401
        with factory() as session:
            assert session.get(AuthActionToken, token_hash) is None
            assert len(list(session.scalars(select(AuthSession)))) == 0

        old_login = client.post("/login", data={
            "email": "owner@example.dz",
            "password": "correct-horse-battery",
        })
        assert old_login.status_code == 401
        new_login = client.post("/login", data={
            "email": "owner@example.dz",
            "password": "new-correct-horse-battery",
        }, follow_redirects=False)
        assert new_login.status_code == 303

        replay = client.post("/reset-password", data={
            "token": reset_token,
            "password": "another-new-correct-password",
            "password_confirm": "another-new-correct-password",
        })
        assert replay.status_code in {400, 422}
    finally:
        client.close()
        engine.dispose()


def test_verification_token_expiry_fails_closed(tmp_path, monkeypatch):
    client, engine, factory, sent = _make_client(tmp_path, monkeypatch)
    try:
        response = client.post("/register", data={
            "display_name": "مشارك",
            "email": "expired@example.dz",
            "password": "correct-horse-battery",
            "role": "participant",
        }, follow_redirects=False)
        assert response.status_code == 303
        token = _token_from_message(sent[-1])
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        with factory() as session, session.begin():
            row = session.get(AuthActionToken, token_hash)
            assert row is not None
            row.expires_at = int(datetime.now(timezone.utc).timestamp()) - 1
        result = client.post("/verify-email", data={"token": token})
        assert result.status_code in {400, 422}
        with factory() as session:
            user = session.scalar(select(User).where(User.email == "expired@example.dz"))
            assert user is not None and user.email_verified_at is None
    finally:
        client.close()
        engine.dispose()


def test_production_cannot_disable_email_verification(monkeypatch):
    from app.auth_flows import email_verification_required

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EMAIL_VERIFICATION_REQUIRED", "false")
    assert email_verification_required() is True
