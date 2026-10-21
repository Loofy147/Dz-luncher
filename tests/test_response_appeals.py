from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import initialize_schema, make_engine, make_session_factory
from app.main import create_app
from app.models import RewardLedgerEntry, RewardObligation, ResponseAppeal, ResponseReview, SurveyResponse, User
from app.response_moderation import review_held_response
from app.services import ServiceError, campaign_report, create_draft, fund_campaign, publish_campaign, register_user, submit_response


def _payload():
    return {
        "title": "اختبار الاعتراض",
        "objective": "التحقق من تجربة خدمة محلية.",
        "description": "دراسة لاختبار مسار الاعتراض.",
        "reward_per_response_dzd": 10, "response_limit": 2, "quotas": {}, "hypotheses": [],
        "questions": [
            {"id": "q1", "text": "الولاية", "kind": "single", "options": [{"id": "a", "label": "الجزائر"}, {"id": "b", "label": "وهران"}]},
            {"id": "q2", "text": "هل استخدمت الخدمة؟", "kind": "single", "options": [{"id": "yes", "label": "نعم"}, {"id": "no", "label": "لا"}], "disqualify_if": ["no"]},
            {"id": "q3", "text": "عدد الاستخدامات", "kind": "number", "lo": 1, "hi": 30},
            {"id": "q4", "text": "التقييم", "kind": "scale", "lo": 1, "hi": 5, "grid": "rating"},
            {"id": "q5", "text": "اختر محايد", "kind": "single", "options": [{"id": "agree", "label": "موافق"}, {"id": "neutral", "label": "محايد"}], "attention_expected": "neutral"},
            {"id": "q6", "text": "هل ستجرب؟", "kind": "single", "options": [{"id": "yes", "label": "نعم"}, {"id": "no", "label": "لا"}]},
            {"id": "q7", "text": "ملاحظات", "kind": "text", "required": False},
        ],
    }


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SESSION_SECRET", "appeal-test-session-secret-with-at-least-32-bytes")
    monkeypatch.setenv("PSEUDONYM_SECRET", "appeal-test-pseudonym-secret-with-at-least-32-bytes")
    engine = make_engine(f"sqlite:///{tmp_path / 'appeals.db'}")
    initialize_schema(engine)
    factory = make_session_factory(engine)
    owner = register_user(factory, email="appeal-owner@example.dz", password="correct-horse-battery", display_name="صاحب الدراسة", role="business")
    participant = register_user(factory, email="appeal-person@example.dz", password="correct-horse-battery", display_name="المشارك", role="participant")
    other = register_user(factory, email="appeal-other@example.dz", password="correct-horse-battery", display_name="مشارك آخر", role="participant")
    admin = register_user(factory, email="appeal-admin@example.dz", password="correct-horse-battery", display_name="المشغّل", role="participant")
    with factory() as session, session.begin():
        session.get(User, admin.id).role = "admin"
    campaign = create_draft(factory, owner.id, _payload())
    fund_campaign(factory, slug_or_id=campaign.slug, amount_dzd=20, reference="appeal-funding", idempotency_key="appeal-funding")
    campaign, version = publish_campaign(factory, owner.id, campaign.slug)
    response = submit_response(factory, slug=campaign.slug, participant_id=participant.id, payload={
        "submission_id": "appeal-held-response", "survey_version_id": version.version_id, "seconds": 1,
        "answers": {"q1": "a", "q2": "yes", "q3": "3", "q4": "4", "q5": "agree", "q6": "yes", "q7": "تعليق يختلف عن غيره في الاختبار"},
    })
    assert response["status"] == "hold"
    review_held_response(factory, response_id=response["response_id"], reviewer_id=admin.id, decision="reject",
        reason_code="unusable_response", note="بعد المراجعة الأولية، لا تتوافق الإجابة مع معايير الجودة المعلنة.")
    app = create_app(engine=engine, session_factory=factory, initialize=False)
    return engine, factory, app, owner, participant, other, admin, campaign, response["response_id"]


def _login(client, email, page):
    response = client.post("/login", data={"email": email, "password": "correct-horse-battery"}, follow_redirects=False)
    assert response.status_code == 303
    html = client.get(page)
    assert html.status_code == 200
    token = re.search(r'<meta name="csrf-token" content="([^"]+)"', html.text)
    assert token
    return token.group(1)


def _appeal(client, csrf, response_id):
    result = client.post(f"/my-responses/{response_id}/appeal", data={
        "csrf_token": csrf,
        "reason": "أرجو إعادة النظر لأنني اتبعت التعليمات وكانت إجاباتي متسقة مع تجربتي الفعلية.",
    }, follow_redirects=False)
    assert result.status_code == 303


def test_participant_can_appeal_only_own_final_rejection_once(tmp_path, monkeypatch):
    engine, factory, app, _, participant, other, _, _, response_id = _setup(tmp_path, monkeypatch)
    client, other_client = TestClient(app), TestClient(app)
    try:
        csrf = _login(client, participant.email, "/my-responses")
        other_csrf = _login(other_client, other.email, "/my-responses")
        foreign = other_client.post(f"/my-responses/{response_id}/appeal", data={
            "csrf_token": other_csrf, "reason": "أطلب إعادة النظر في هذه الاستجابة رغم أنها ليست حسابي.",
        }, follow_redirects=False)
        assert foreign.status_code == 404
        _appeal(client, csrf, response_id)
        history = client.get("/my-responses")
        assert "اعتراض قيد المراجعة" in history.text
        replay = client.post(f"/my-responses/{response_id}/appeal", data={
            "csrf_token": csrf, "reason": "أكرر طلب المراجعة مع مزيد من التوضيح حول إجاباتي.",
        }, follow_redirects=False)
        assert replay.status_code == 409
        with factory() as session:
            appeals = list(session.scalars(select(ResponseAppeal)))
            assert len(appeals) == 1 and appeals[0].status == "open"
    finally:
        client.close()
        other_client.close()
        engine.dispose()


def test_overturning_appeal_restores_accepted_state_and_reserves_reward_once(tmp_path, monkeypatch):
    engine, factory, app, owner, participant, _, admin, campaign, response_id = _setup(tmp_path, monkeypatch)
    client, admin_client = TestClient(app), TestClient(app)
    try:
        csrf = _login(client, participant.email, "/my-responses")
        _appeal(client, csrf, response_id)
        admin_csrf = _login(admin_client, admin.email, "/admin/response-appeals")
        with factory() as session:
            appeal = session.scalar(select(ResponseAppeal).where(ResponseAppeal.response_id == response_id))
            assert appeal is not None
            appeal_id = appeal.id
        result = admin_client.post(f"/admin/response-appeals/{appeal_id}", data={
            "csrf_token": admin_csrf, "decision": "overturn",
            "resolution_note": "راجعت اللجنة الأدلة وألغت الرفض السابق بعد التأكد من مطابقة الشروط.",
        }, follow_redirects=False)
        assert result.status_code == 303

        with factory() as session:
            appeal = session.get(ResponseAppeal, appeal_id)
            response = session.get(SurveyResponse, response_id)
            review = session.scalar(select(ResponseReview).where(ResponseReview.response_id == response_id))
            obligation = session.scalar(select(RewardObligation).where(RewardObligation.response_id == response_id))
            assert appeal is not None and appeal.status == "overturned" and appeal.closed_at is not None
            assert response is not None and response.status == "accepted_flagged"
            assert review is not None and review.decision == "reject"  # Preserve original decision for audit.
            assert obligation is not None and obligation.status == "pending" and obligation.amount_dzd == 10
            entries = list(session.scalars(select(RewardLedgerEntry).where(RewardLedgerEntry.survey_id == campaign.id)))
            assert len([entry for entry in entries if entry.event_type == "reward_reserved"]) == 1
            assert sum(entry.available_delta_dzd for entry in entries) == 10
            assert sum(entry.obligated_delta_dzd for entry in entries) == 10
        report = campaign_report(factory, slug=campaign.slug, owner_id=owner.id)
        assert report["accepted_n"] == 1
        assert report["sample_flow"]["accepted_flagged"] == 1
        assert report["sample_flow"].get("review_rejected", 0) == 0
        with pytest.raises(ServiceError) as raised:
            from app.response_appeals import resolve_response_appeal
            resolve_response_appeal(factory, appeal_id=appeal_id, reviewer_id=admin.id, decision="uphold",
                resolution_note="لا يمكن تغيير قرار اعتراض نهائي سبق تسجيله.")
        assert raised.value.code == "response_appeal_already_resolved"
    finally:
        client.close()
        admin_client.close()
        engine.dispose()


def test_upholding_appeal_does_not_create_reward_and_keeps_rejection_in_report(tmp_path, monkeypatch):
    engine, factory, app, owner, participant, _, admin, campaign, response_id = _setup(tmp_path, monkeypatch)
    client, admin_client = TestClient(app), TestClient(app)
    try:
        csrf = _login(client, participant.email, "/my-responses")
        _appeal(client, csrf, response_id)
        admin_csrf = _login(admin_client, admin.email, "/admin/response-appeals")
        with factory() as session:
            appeal = session.scalar(select(ResponseAppeal).where(ResponseAppeal.response_id == response_id))
            assert appeal is not None
        result = admin_client.post(f"/admin/response-appeals/{appeal.id}", data={
            "csrf_token": admin_csrf, "decision": "uphold",
            "resolution_note": "راجعت اللجنة الاعتراض ولم يظهر دليل يكفي لتغيير قرار المراجعة الأول.",
        }, follow_redirects=False)
        assert result.status_code == 303
        with factory() as session:
            appeal = session.get(ResponseAppeal, appeal.id)
            response = session.get(SurveyResponse, response_id)
            obligations = list(session.scalars(select(RewardObligation).where(RewardObligation.response_id == response_id)))
            assert appeal is not None and appeal.status == "upheld"
            assert response is not None and response.status == "hold"
            assert not obligations
        report = campaign_report(factory, slug=campaign.slug, owner_id=owner.id)
        assert report["accepted_n"] == 0
        assert report["sample_flow"]["review_rejected"] == 1
    finally:
        client.close()
        admin_client.close()
        engine.dispose()
