from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app.db import initialize_schema, make_engine, make_session_factory
from app.models import RewardLedgerEntry, RewardObligation, SurveyResponse
from app.services import (
    ServiceError, campaign_report, create_draft, fund_campaign, mark_reward_paid,
    publish_campaign, register_user, submit_response,
)


@pytest.fixture

def system(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-at-least-32-bytes-long")
    monkeypatch.setenv("PSEUDONYM_SECRET", "test-pseudonym-secret-at-least-32-bytes-long")
    engine = make_engine(f"sqlite:///{tmp_path / 'survey.db'}")
    initialize_schema(engine)
    factory = make_session_factory(engine)
    business = register_user(factory, email="owner@example.dz", password="correct-horse-battery", display_name="صاحب المشروع", role="business")
    participants = [
        register_user(factory, email=f"participant{i}@example.dz", password="correct-horse-battery", display_name=f"مشارك {i}", role="participant")
        for i in range(1, 5)
    ]
    yield factory, business, participants
    engine.dispose()


def payload(*, reward=0, limit=10, quotas=None, hypotheses=None):
    return {
        "title": "اختبار خدمة توصيل",
        "objective": "التحقق من أولويات المستخدمين قبل إطلاق الخدمة.",
        "description": "دراسة تجريبية لتوضيح طريقة عمل المنصة.",
        "reward_per_response_dzd": reward,
        "response_limit": limit,
        "quotas": quotas or {},
        "hypotheses": hypotheses or [],
        "questions": [
            {"id": "q1", "text": "في أي ولاية تقيم؟", "kind": "single", "options": [
                {"id": "option_1", "label": "الجزائر"}, {"id": "option_2", "label": "وهران"}, {"id": "option_3", "label": "ولاية أخرى"}
            ]},
            {"id": "q2", "text": "هل استخدمت الخدمة مؤخراً؟", "kind": "single", "options": [
                {"id": "option_1", "label": "نعم"}, {"id": "option_2", "label": "لا"}
            ], "disqualify_if": ["option_2"]},
            {"id": "q3", "text": "كم مرة استخدمت الخدمة؟", "kind": "number", "lo": 1, "hi": 60,
             "show_if": {"question_id": "q2", "any_of": ["option_1"]}},
            {"id": "q4", "text": "قيّم التجربة من 1 إلى 5", "kind": "scale", "lo": 1, "hi": 5, "grid": "rating"},
            {"id": "q5", "text": "لأجل التحقق اختر محايد", "kind": "single", "options": [
                {"id": "option_1", "label": "موافق"}, {"id": "option_2", "label": "محايد"}, {"id": "option_3", "label": "غير موافق"}
            ], "attention_expected": "option_2"},
            {"id": "q6", "text": "هل ستجرّب الخدمة؟", "kind": "single", "options": [
                {"id": "option_1", "label": "نعم"}, {"id": "option_2", "label": "لا"}
            ]},
            {"id": "q7", "text": "ملاحظات أخرى", "kind": "text", "required": False},
        ],
    }


def create_published(factory, business, *, reward=0, limit=10, quotas=None, hypotheses=None, funding=None):
    campaign = create_draft(factory, business.id, payload(reward=reward, limit=limit, quotas=quotas, hypotheses=hypotheses))
    if funding:
        fund_campaign(factory, slug_or_id=campaign.slug, amount_dzd=funding, reference="bank-confirmation-001", idempotency_key=f"fund:{campaign.slug}:001")
    campaign, version = publish_campaign(factory, business.id, campaign.slug)
    return campaign, version


def valid_response(version_id, submission_id="submission-1", *, q1="option_1", q2="option_1", q3="3", q4="4", q5="option_2", q6="option_1", comment="تجربة مفيدة لكنها تحتاج تحسيناً"):
    return {
        "submission_id": submission_id,
        "survey_version_id": version_id,
        "seconds": 120,
        "answers": {"q1": q1, "q2": q2, "q3": q3, "q4": q4, "q5": q5, "q6": q6, "q7": comment},
    }


def test_funding_is_required_before_publishing_rewarded_campaign(system):
    factory, business, _ = system
    campaign = create_draft(factory, business.id, payload(reward=25, limit=4))
    with pytest.raises(ServiceError) as raised:
        publish_campaign(factory, business.id, campaign.slug)
    assert raised.value.code == "insufficient_campaign_funding"


def test_funding_is_idempotent_and_conflicts_fail_closed(system):
    factory, business, _ = system
    campaign = create_draft(factory, business.id, payload(reward=5, limit=2))
    first = fund_campaign(factory, slug_or_id=campaign.slug, amount_dzd=10, reference="receipt-01", idempotency_key="funding-01")
    replay = fund_campaign(factory, slug_or_id=campaign.slug, amount_dzd=10, reference="receipt-01", idempotency_key="funding-01")
    assert first["available_dzd"] == replay["available_dzd"] == 10
    assert replay["idempotent_replay"] is True
    with pytest.raises(ServiceError) as raised:
        fund_campaign(factory, slug_or_id=campaign.slug, amount_dzd=11, reference="receipt-01", idempotency_key="funding-01")
    assert raised.value.code == "funding_idempotency_conflict"


def test_accepted_response_reserves_one_reward_and_retry_does_not_duplicate_it(system):
    factory, business, people = system
    campaign, version = create_published(factory, business, reward=20, limit=2, funding=40)
    body = valid_response(version.version_id)
    first = submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=body)
    replay = submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=body)
    assert first["status"] in {"accepted", "accepted_flagged"}
    assert first["reward_status"] == "pending" and first["reward_amount_dzd"] == 20
    assert replay["idempotent_replay"] is True
    assert replay["response_id"] == first["response_id"]
    with factory() as session:
        ledger = list(session.scalars(select(RewardLedgerEntry).where(RewardLedgerEntry.survey_id == campaign.id)))
        obligations = list(session.scalars(select(RewardObligation).where(RewardObligation.survey_id == campaign.id)))
    assert len([row for row in ledger if row.event_type == "reward_reserved"]) == 1
    assert len(obligations) == 1
    assert sum(row.available_delta_dzd for row in ledger) == 20
    assert sum(row.obligated_delta_dzd for row in ledger) == 20


def test_same_id_with_changed_payload_returns_idempotency_conflict(system):
    factory, business, people = system
    campaign, version = create_published(factory, business, limit=2)
    first = valid_response(version.version_id, "same-id")
    submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=first)
    changed = valid_response(version.version_id, "same-id", q6="option_2")
    with pytest.raises(ServiceError) as raised:
        submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=changed)
    assert raised.value.code == "idempotency_conflict"


def test_screen_out_is_not_a_quality_hold_and_does_not_earn_reward(system):
    factory, business, people = system
    campaign, version = create_published(factory, business, reward=20, limit=2, funding=40)
    answer = valid_response(version.version_id, "screened", q2="option_2")
    answer["answers"] = {"q1": "option_1", "q2": "option_2"}
    result = submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=answer)
    assert result["status"] == "screened_out"
    assert result["reward_status"] == "not_earned"
    with factory() as session:
        assert session.scalar(select(RewardObligation).where(RewardObligation.response_id == result["response_id"])) is None


def test_database_quota_is_enforced_between_submissions(system):
    factory, business, people = system
    campaign, version = create_published(factory, business, limit=4, quotas={"q1": {"option_1": 1}})
    first = submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=valid_response(version.version_id, "quota-1", q1="option_1"))
    second = submit_response(factory, slug=campaign.slug, participant_id=people[1].id, payload=valid_response(version.version_id, "quota-2", q1="option_1", q4="2", comment="أحتاج خيارات أخرى للتوصيل"))
    assert first["status"] in {"accepted", "accepted_flagged"}
    assert second["status"] == "quota_full"


def test_screener_branch_and_duplicate_participant_policy(system):
    factory, business, people = system
    campaign, version = create_published(factory, business, limit=4)
    screened = valid_response(version.version_id, "screened-first", q2="option_2")
    screened["answers"] = {"q1": "option_1", "q2": "option_2"}
    result = submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=screened)
    assert result["status"] == "screened_out"
    retry = submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=valid_response(version.version_id, "try-again"))
    assert retry["status"] == "excluded_duplicate"


def test_reward_fulfillment_moves_obligation_to_paid_once(system):
    factory, business, people = system
    campaign, version = create_published(factory, business, reward=15, limit=1, funding=15)
    result = submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=valid_response(version.version_id))
    with factory() as session:
        obligation = session.scalar(select(RewardObligation).where(RewardObligation.response_id == result["response_id"]))
        obligation_id = obligation.id
    paid = mark_reward_paid(factory, obligation_id=obligation_id, reference="transfer-proof-001")
    replay = mark_reward_paid(factory, obligation_id=obligation_id, reference="transfer-proof-001")
    assert paid["status"] == "paid" and replay["idempotent_replay"] is True
    with factory() as session:
        ledger = list(session.scalars(select(RewardLedgerEntry).where(RewardLedgerEntry.survey_id == campaign.id)))
    assert sum(row.available_delta_dzd for row in ledger) == 0
    assert sum(row.obligated_delta_dzd for row in ledger) == 0
    assert sum(row.paid_delta_dzd for row in ledger) == 15


def test_campaign_limit_cannot_be_overfilled(system):
    factory, business, people = system
    campaign, version = create_published(factory, business, limit=1)
    accepted = submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=valid_response(version.version_id, "limit-1"))
    assert accepted["status"] in {"accepted", "accepted_flagged"}
    with pytest.raises(ServiceError) as raised:
        submit_response(factory, slug=campaign.slug, participant_id=people[1].id, payload=valid_response(version.version_id, "limit-2", q1="option_2"))
    assert raised.value.code == "campaign_full"


def test_report_labels_declared_hypotheses_as_declared_only(system):
    factory, business, people = system
    hs = [{"id": "H1", "question_id": "q6", "positive_values": ["option_1"], "threshold": 0.4, "minimum_n": 1, "evidence_type": "declared"}]
    campaign, version = create_published(factory, business, limit=5, hypotheses=hs)
    submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=valid_response(version.version_id))
    report = campaign_report(factory, slug=campaign.slug, owner_id=business.id)
    assert report["sample_flow"]["accepted"] + report["sample_flow"]["accepted_flagged"] == 1
    assert report["hypotheses"][0]["evidence_scope"] == "declared_only"
    assert report["hypotheses"][0]["demand_validation_eligible"] is False
    assert any("voluntary" in item.lower() for item in report["limitations"])


def test_non_owner_cannot_read_campaign_report(system):
    factory, business, people = system
    campaign, _ = create_published(factory, business, limit=3)
    with pytest.raises(ServiceError) as raised:
        campaign_report(factory, slug=campaign.slug, owner_id=people[0].id)
    assert raised.value.status_code == 403


def test_concurrent_submissions_cannot_overfill_campaign_limit(system):
    factory, business, people = system
    campaign, version = create_published(factory, business, limit=1)

    def try_submit(person, submission_id, q1):
        try:
            result = submit_response(factory, slug=campaign.slug, participant_id=person.id,
                                     payload=valid_response(version.version_id, submission_id, q1=q1, comment=f"ملاحظة {submission_id} مختلفة"))
            return result["status"]
        except ServiceError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda item: try_submit(*item), [
            (people[0], "race-1", "option_1"), (people[1], "race-2", "option_2"),
        ]))
    accepted = sum(value in {"accepted", "accepted_flagged"} for value in outcomes)
    assert accepted == 1, outcomes
    assert outcomes.count("campaign_full") == 1, outcomes
    with factory() as session:
        accepted_count = session.scalar(select(func.count()).select_from(SurveyResponse).where(
            SurveyResponse.survey_id == campaign.id, SurveyResponse.status.in_(("accepted", "accepted_flagged"))
        ))
    assert accepted_count == 1


def test_campaign_contract_rejects_unknown_input_fields(system):
    factory, business, _ = system
    bad = payload()
    bad["administrator_override"] = True
    with pytest.raises(ServiceError) as raised:
        create_draft(factory, business.id, bad)
    assert raised.value.code == "unknown_campaign_fields"


def test_publishing_does_not_allow_non_owner_to_publish(system):
    factory, business, people = system
    campaign = create_draft(factory, business.id, payload())
    with pytest.raises(ServiceError) as raised:
        publish_campaign(factory, people[0].id, campaign.slug)
    assert raised.value.status_code == 403


def test_operator_labels_are_recorded_in_reward_audit_events(system):
    factory, business, people = system
    campaign, version = create_published(factory, business, reward=10, limit=1, funding=10)
    result = submit_response(factory, slug=campaign.slug, participant_id=people[0].id, payload=valid_response(version.version_id))
    with factory() as session:
        obligation = session.scalar(select(RewardObligation).where(RewardObligation.response_id == result["response_id"]))
        obligation_id = obligation.id
    mark_reward_paid(factory, obligation_id=obligation_id, reference="external-payment-42", operator_label="ops on duty")
    with factory() as session:
        from app.models import AuditEvent
        audit = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "reward.marked_paid"))
        details = json.loads(audit.details_json)
    assert details["operator_label"] == "ops on duty"
    assert details["reference"] == "external-payment-42"
