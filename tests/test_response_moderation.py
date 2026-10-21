from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import initialize_schema, make_engine, make_session_factory
from app.main import create_app
from app.models import RewardLedgerEntry, RewardObligation, ResponseReview, SurveyResponse, User
from app.services import (
    ServiceError, campaign_report, create_draft, fund_campaign, publish_campaign,
    register_user, submit_response,
)
from app.response_moderation import review_held_response


def _payload(reward: int = 10, limit: int = 2) -> dict:
    return {
        "title": "دراسة اختبار المراجعة",
        "objective": "التحقق من تجربة خدمة محلية.",
        "description": "قالب دراسة اختبار داخلي.",
        "reward_per_response_dzd": reward,
        "response_limit": limit,
        "quotas": {},
        "hypotheses": [],
        "questions": [
            {"id": "q1", "text": "في أي ولاية تقيم؟", "kind": "single", "options": [
                {"id": "option_1", "label": "الجزائر"}, {"id": "option_2", "label": "وهران"},
            ]},
            {"id": "q2", "text": "هل استخدمت الخدمة مؤخراً؟", "kind": "single", "options": [
                {"id": "option_1", "label": "نعم"}, {"id": "option_2", "label": "لا"},
            ], "disqualify_if": ["option_2"]},
            {"id": "q3", "text": "كم مرة استخدمت الخدمة؟", "kind": "number", "lo": 1, "hi": 30},
            {"id": "q4", "text": "قيّم التجربة", "kind": "scale", "lo": 1, "hi": 5, "grid": "rating"},
            {"id": "q5", "text": "لأجل التحقق اختر محايد", "kind": "single", "options": [
                {"id": "option_1", "label": "موافق"}, {"id": "option_2", "label": "محايد"},
            ], "attention_expected": "option_2"},
            {"id": "q6", "text": "هل ستجرب الخدمة؟", "kind": "single", "options": [
                {"id": "option_1", "label": "نعم"}, {"id": "option_2", "label": "لا"},
            ]},
            {"id": "q7", "text": "ملاحظات إضافية", "kind": "text", "required": False},
        ],
    }


def _held_response(factory, campaign, version, participant_id: str, submission_id: str) -> dict:
    return submit_response(
        factory,
        slug=campaign.slug,
        participant_id=participant_id,
        payload={
            "submission_id": submission_id,
            "survey_version_id": version.version_id,
            "seconds": 1,
            "answers": {
                "q1": "option_1", "q2": "option_1", "q3": "3", "q4": "4",
                "q5": "option_1", "q6": "option_1", "q7": "تعليق تجريبي مختلف لهذه الحالة",
            },
        },
    )


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SESSION_SECRET", "moderation-test-session-secret-at-least-32-bytes")
    monkeypatch.setenv("PSEUDONYM_SECRET", "moderation-test-pseudonym-secret-at-least-32-bytes")
    engine = make_engine(f"sqlite:///{tmp_path / 'moderation.db'}")
    initialize_schema(engine)
    factory = make_session_factory(engine)
    owner = register_user(factory, email="moderation-owner@example.dz", password="correct-horse-battery", display_name="صاحب الدراسة", role="business")
    person1 = register_user(factory, email="moderation-person1@example.dz", password="correct-horse-battery", display_name="مشارك أول", role="participant")
    person2 = register_user(factory, email="moderation-person2@example.dz", password="correct-horse-battery", display_name="مشارك ثان", role="participant")
    admin = register_user(factory, email="moderation-admin@example.dz", password="correct-horse-battery", display_name="مشغّل", role="participant")
    with factory() as session, session.begin():
        session.get(User, admin.id).role = "admin"
    campaign = create_draft(factory, owner.id, _payload())
    fund_campaign(
        factory, slug_or_id=campaign.slug, amount_dzd=20, reference="verified-funding-01",
        idempotency_key="moderation-funding-01",
    )
    campaign, version = publish_campaign(factory, owner.id, campaign.slug)
    app = create_app(engine=engine, session_factory=factory, initialize=False)
    return engine, factory, app, owner, person1, person2, admin, campaign, version


def _admin_client(app):
    client = TestClient(app)
    logged = client.post("/login", data={
        "email": "moderation-admin@example.dz", "password": "correct-horse-battery",
    }, follow_redirects=False)
    assert logged.status_code == 303
    page = client.get("/admin/response-reviews")
    assert page.status_code == 200
    token = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text)
    assert token
    return client, token.group(1)


def test_admin_accepting_held_response_reserves_reward_once_and_removes_it_from_queue(tmp_path, monkeypatch):
    engine, factory, app, owner, person1, _, _, campaign, version = _setup(tmp_path, monkeypatch)
    client, csrf = _admin_client(app)
    try:
        held = _held_response(factory, campaign, version, person1.id, "held-accept-01")
        assert held["status"] == "hold"
        queue = client.get("/admin/response-reviews")
        assert "دراسة اختبار المراجعة" in queue.text
        assert held["response_id"] in queue.text

        decision = client.post(f"/admin/response-reviews/{held['response_id']}", data={
            "csrf_token": csrf,
            "decision": "accept",
            "reason_code": "valid_response",
            "note": "راجعت السياق والإجابات؛ الاستجابة مستوفية لشروط الدراسة.",
        }, follow_redirects=False)
        assert decision.status_code == 303

        with factory() as session:
            response = session.get(SurveyResponse, held["response_id"])
            review = session.scalar(select(ResponseReview).where(ResponseReview.response_id == held["response_id"]))
            obligation = session.scalar(select(RewardObligation).where(RewardObligation.response_id == held["response_id"]))
            assert response is not None and response.status == "accepted_flagged"
            assert review is not None and review.decision == "accept"
            assert obligation is not None and obligation.status == "pending" and obligation.amount_dzd == 10
            ledger = list(session.scalars(select(RewardLedgerEntry).where(RewardLedgerEntry.survey_id == campaign.id)))
            assert len([entry for entry in ledger if entry.event_type == "reward_reserved"]) == 1
            assert sum(entry.available_delta_dzd for entry in ledger) == 10
            assert sum(entry.obligated_delta_dzd for entry in ledger) == 10

        queue_after = client.get("/admin/response-reviews")
        assert held["response_id"] not in queue_after.text

        with pytest.raises(ServiceError) as raised:
            # Only held responses with no completed review can enter the review transition.
            review_held_response(
                factory, response_id=held["response_id"], reviewer_id=owner.id,
                decision="reject", reason_code="unusable_response", note="قرار مكرر",
            )
        assert raised.value.code in {"response_not_held", "response_already_reviewed"}
    finally:
        client.close()
        engine.dispose()


def test_rejected_review_is_audited_without_creating_a_reward_and_is_separated_in_report(tmp_path, monkeypatch):
    engine, factory, app, _, person1, _, _, campaign, version = _setup(tmp_path, monkeypatch)
    client, csrf = _admin_client(app)
    try:
        held = _held_response(factory, campaign, version, person1.id, "held-reject-01")
        assert held["status"] == "hold"
        response = client.post(f"/admin/response-reviews/{held['response_id']}", data={
            "csrf_token": csrf,
            "decision": "reject",
            "reason_code": "unusable_response",
            "note": "بعد المراجعة، لا تتوافق الإجابة مع معايير الجودة المعلنة.",
        }, follow_redirects=False)
        assert response.status_code == 303
        with factory() as session:
            review = session.scalar(select(ResponseReview).where(ResponseReview.response_id == held["response_id"]))
            obligation = session.scalar(select(RewardObligation).where(RewardObligation.response_id == held["response_id"]))
            assert review is not None and review.decision == "reject"
            assert obligation is None

        report = campaign_report(factory, slug=campaign.slug, owner_id=campaign.owner_id)
        assert report["sample_flow"]["review_rejected"] == 1
        assert report["accepted_n"] == 0
    finally:
        client.close()
        engine.dispose()
