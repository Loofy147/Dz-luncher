from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.db import initialize_schema, make_engine, make_session_factory
from app.main import create_app
from app.models import Notification
from app.services import register_user


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SESSION_SECRET", "notification-test-session-secret-with-at-least-32-bytes")
    monkeypatch.setenv("PSEUDONYM_SECRET", "notification-test-pseudonym-secret-with-at-least-32-bytes")
    engine = make_engine(f"sqlite:///{tmp_path / 'notifications.db'}")
    initialize_schema(engine)
    factory = make_session_factory(engine)
    first = register_user(factory, email="notify-first@example.dz", password="correct-horse-battery", display_name="المستخدم الأول", role="participant")
    second = register_user(factory, email="notify-second@example.dz", password="correct-horse-battery", display_name="المستخدم الثاني", role="participant")
    with factory() as session, session.begin():
        own = Notification(
            id="a".ljust(32, "a"),
            user_id=first.id,
            event_type="response.hold",
            title="استجابتك قيد المراجعة",
            body="وصلت الاستجابة إلى مراجعة بشرية، وهذا لا يعني رفضاً تلقائياً.",
            target_path="/my-responses",
        )
        foreign = Notification(
            id="b".ljust(32, "b"),
            user_id=second.id,
            event_type="response.accepted",
            title="إشعار خاص بحساب آخر",
            body="هذا الإشعار يجب ألا يظهر للمستخدم الأول.",
            target_path="/my-responses",
        )
        session.add_all([own, foreign])
    app = create_app(engine=engine, session_factory=factory, initialize=False)
    return engine, factory, app, first, second, own.id, foreign.id


def _login(client: TestClient, email: str) -> str:
    response = client.post("/login", data={"email": email, "password": "correct-horse-battery"}, follow_redirects=False)
    assert response.status_code == 303
    page = client.get("/notifications")
    assert page.status_code == 200
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text)
    assert match
    return match.group(1)


def test_notifications_are_private_and_mark_as_read_is_durable(tmp_path, monkeypatch):
    engine, factory, app, first, second, own_id, _ = _setup(tmp_path, monkeypatch)
    client = TestClient(app)
    other_client = TestClient(app)
    try:
        csrf = _login(client, first.email)
        own_page = client.get("/notifications")
        assert "استجابتك قيد المراجعة" in own_page.text
        assert "إشعار خاص بحساب آخر" not in own_page.text
        assert "غير مقروء" in own_page.text

        marked = client.post(f"/notifications/{own_id}/read", data={"csrf_token": csrf}, follow_redirects=False)
        assert marked.status_code == 303
        with factory() as session:
            own = session.get(Notification, own_id)
            assert own is not None and own.read_at is not None
        assert "مقروء" in client.get("/notifications").text

        other_csrf = _login(other_client, second.email)
        forbidden = other_client.post(f"/notifications/{own_id}/read", data={"csrf_token": other_csrf}, follow_redirects=False)
        assert forbidden.status_code == 404
        assert client.get("/notifications").status_code == 200
    finally:
        client.close()
        other_client.close()
        engine.dispose()


def test_marking_notification_read_is_idempotent_and_does_not_change_event_payload(tmp_path, monkeypatch):
    engine, factory, app, first, _, own_id, _ = _setup(tmp_path, monkeypatch)
    client = TestClient(app)
    try:
        csrf = _login(client, first.email)
        client.post(f"/notifications/{own_id}/read", data={"csrf_token": csrf}, follow_redirects=False)
        with factory() as session:
            original = session.get(Notification, own_id)
            assert original is not None and original.read_at is not None
            first_read_at = original.read_at
            original_body = original.body

        response = client.post(f"/notifications/{own_id}/read", data={"csrf_token": csrf}, follow_redirects=False)
        assert response.status_code == 303
        with factory() as session:
            replay = session.get(Notification, own_id)
            assert replay is not None and replay.read_at == first_read_at
            assert replay.body == original_body
            assert replay.event_type == "response.hold"
    finally:
        client.close()
        engine.dispose()
