from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import initialize_schema, make_engine, make_session_factory
from app.main import create_app
from app.models import AuditEvent, DataSubjectRequest, User


def _signup(client: TestClient, *, email: str, role: str = "participant") -> str:
    response = client.post("/register", data={
        "display_name": email.split("@", 1)[0],
        "email": email,
        "password": "correct-horse-battery",
        "role": role,
    }, follow_redirects=True)
    assert response.status_code == 200
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.text)
    assert match
    return match.group(1)


def _system(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SESSION_SECRET", "privacy-test-session-secret-with-at-least-32-bytes")
    monkeypatch.setenv("PSEUDONYM_SECRET", "privacy-test-pseudonym-secret-with-at-least-32-bytes")
    engine = make_engine(f"sqlite:///{tmp_path / 'privacy-requests.db'}")
    initialize_schema(engine)
    factory = make_session_factory(engine)
    app = create_app(engine=engine, session_factory=factory, initialize=False)
    return engine, factory, app


def test_privacy_request_is_private_to_requester_and_records_only_minimal_audit_metadata(tmp_path, monkeypatch):
    engine, factory, app = _system(tmp_path, monkeypatch)
    first = TestClient(app)
    second = TestClient(app)
    try:
        csrf_first = _signup(first, email="first@example.dz")
        _signup(second, email="second@example.dz")

        page = first.get("/privacy-requests")
        assert page.status_code == 200
        assert "طلب خصوصية" in page.text
        submitted = first.post("/privacy-requests", data={
            "csrf_token": csrf_first,
            "request_type": "access",
            "details": "أريد معرفة البيانات المرتبطة بحسابي.",
        }, follow_redirects=False)
        assert submitted.status_code == 303
        assert submitted.headers["location"] == "/privacy-requests?notice=request_submitted"

        first_page = first.get("/privacy-requests")
        second_page = second.get("/privacy-requests")
        assert "أريد معرفة البيانات المرتبطة بحسابي" in first_page.text
        assert "أريد معرفة البيانات المرتبطة بحسابي" not in second_page.text

        with factory() as session:
            row = session.scalar(select(DataSubjectRequest))
            assert row is not None
            assert row.request_type == "access"
            assert row.status == "open"
            audit = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "privacy_request.created"))
            assert audit is not None
            assert "أريد معرفة البيانات" not in audit.details_json
    finally:
        first.close()
        second.close()
        engine.dispose()


def test_only_admin_can_triage_requests_and_terminal_state_requires_a_resolution_note(tmp_path, monkeypatch):
    engine, factory, app = _system(tmp_path, monkeypatch)
    client = TestClient(app)
    try:
        csrf = _signup(client, email="requester@example.dz", role="business")
        create = client.post("/privacy-requests", data={
            "csrf_token": csrf,
            "request_type": "deletion",
            "details": "أطلب مراجعة حذف بيانات الحساب وفق السياسة المعتمدة.",
        }, follow_redirects=False)
        assert create.status_code == 303

        assert client.get("/admin/privacy-requests").status_code == 403
        with factory() as session, session.begin():
            user = session.scalar(select(User).where(User.email == "requester@example.dz"))
            assert user is not None
            user.role = "admin"

        queue = client.get("/admin/privacy-requests")
        assert queue.status_code == 200
        assert "حذف بيانات الحساب" in queue.text
        with factory() as session:
            request_row = session.scalar(select(DataSubjectRequest))
            assert request_row is not None
            request_id = request_row.id

        no_note = client.post(f"/admin/privacy-requests/{request_id}", data={
            "csrf_token": csrf,
            "status": "completed",
            "resolution_note": "",
        })
        assert no_note.status_code == 422

        updated = client.post(f"/admin/privacy-requests/{request_id}", data={
            "csrf_token": csrf,
            "status": "in_review",
            "resolution_note": "تم تعيين الطلب للمراجعة.",
        }, follow_redirects=False)
        assert updated.status_code == 303

        closed = client.post(f"/admin/privacy-requests/{request_id}", data={
            "csrf_token": csrf,
            "status": "completed",
            "resolution_note": "تم تنفيذ الإجراء وفق السياسة المعتمدة والتحقق من النتيجة.",
        }, follow_redirects=False)
        assert closed.status_code == 303

        with factory() as session:
            row = session.get(DataSubjectRequest, request_id)
            assert row is not None and row.status == "completed" and row.closed_at is not None
            events = list(session.scalars(select(AuditEvent).where(
                AuditEvent.target_type == "privacy_request", AuditEvent.target_id == request_id,
            )))
            assert len(events) == 3
            assert sorted(event.event_type for event in events) == sorted([
                "privacy_request.created", "privacy_request.status_changed", "privacy_request.status_changed"
            ])
            assert all("تم تنفيذ الإجراء" not in event.details_json for event in events)
    finally:
        client.close()
        engine.dispose()
