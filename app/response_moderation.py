"""Human review queue for responses held by automated quality signals."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import (
    RewardLedgerEntry, RewardObligation, ResponseReview, SurveyCampaign,
    SurveyResponse, SurveyVersion, User,
)
from app.services import ServiceError, _audit
from validation_core import ACCEPTED_STATUSES, survey_from_dict

REVIEW_REASONS = {
    "valid_response": "استجابة مستوفية للشروط",
    "ineligible": "عدم مطابقة شروط الأهلية",
    "unusable_response": "إجابة غير قابلة للاستخدام",
    "confirmed_duplicate": "تكرار تم التحقق منه",
    "policy_violation": "مخالفة سياسة الدراسة",
    "other": "سبب آخر موضح في الملاحظة",
}
REJECTION_REASONS = {"ineligible", "unusable_response", "confirmed_duplicate", "policy_violation", "other"}


def list_response_review_queue(session_factory: sessionmaker, *, limit: int = 100) -> list[dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("response_review_limit_must_be_between_1_and_500")
    reviewed_ids = select(ResponseReview.response_id)
    with session_factory() as session:
        responses = list(session.scalars(
            select(SurveyResponse)
            .where(SurveyResponse.status == "hold", ~SurveyResponse.id.in_(reviewed_ids))
            .order_by(SurveyResponse.submitted_at.asc(), SurveyResponse.id)
            .limit(limit)
        ))
        output: list[dict[str, Any]] = []
        for response in responses:
            campaign = session.get(SurveyCampaign, response.survey_id)
            version = session.get(SurveyVersion, response.survey_version_id)
            if campaign is None or version is None:
                continue
            try:
                schema = survey_from_dict(json.loads(version.schema_json))
                answers = json.loads(response.answers_json)
            except (ValueError, TypeError, json.JSONDecodeError):
                schema, answers = None, {}
            answer_items = []
            if schema is not None:
                for question in schema.questions:
                    if question.id not in answers:
                        continue
                    value = answers[question.id]
                    if question.kind == "single":
                        labels = {option.id: option.label for option in question.options}
                        rendered = labels.get(value, "خيار غير معروف")
                    else:
                        rendered = str(value)
                    if question.kind == "text":
                        rendered = rendered[:1000]
                    answer_items.append({"question": question.text, "answer": rendered, "kind": question.kind})
            output.append({
                "response_id": response.id,
                "survey_id": campaign.id,
                "survey_title": campaign.title,
                "survey_slug": campaign.slug,
                "participant_pseudonym": response.pseudonym,
                "submitted_at": response.submitted_at,
                "elapsed_seconds": response.elapsed_seconds,
                "signals": json.loads(response.signals_json),
                "review_groups": json.loads(response.review_groups_json),
                "answers": answer_items,
            })
        return output


def review_held_response(
    session_factory: sessionmaker,
    *,
    response_id: str,
    reviewer_id: str,
    decision: str,
    reason_code: str,
    note: str,
) -> dict[str, Any]:
    if decision not in {"accept", "reject"}:
        raise ServiceError("قرار المراجعة غير صالح.", 422, "invalid_review_decision")
    if decision == "accept" and reason_code != "valid_response":
        raise ServiceError("قبول الاستجابة يتطلب سبب قبول صالحاً.", 422, "invalid_review_reason")
    if decision == "reject" and reason_code not in REJECTION_REASONS:
        raise ServiceError("سبب الرفض غير صالح.", 422, "invalid_review_reason")
    if not isinstance(note, str):
        raise ServiceError("ملاحظة المراجعة غير صالحة.", 422, "invalid_review_note")
    note = note.strip()
    if len(note) < 10 or len(note) > 2000:
        raise ServiceError("ملاحظة المراجعة يجب أن تتراوح بين 10 و2000 حرف.", 422, "invalid_review_note")

    with session_factory() as session:
        candidate = session.get(SurveyResponse, response_id)
        if candidate is None:
            raise ServiceError("الاستجابة غير موجودة.", 404, "response_not_found")
        survey_id = candidate.survey_id

    with session_factory() as session, session.begin():
        reviewer = session.get(User, reviewer_id)
        if reviewer is None or reviewer.role != "admin":
            raise ServiceError("هذه العملية تتطلب مشغّلاً مخوّلاً.", 403, "admin_required")
        campaign = session.scalar(
            select(SurveyCampaign).where(SurveyCampaign.id == survey_id).with_for_update()
        )
        response = session.scalar(
            select(SurveyResponse).where(SurveyResponse.id == response_id).with_for_update()
        )
        if campaign is None or response is None or response.survey_id != survey_id:
            raise ServiceError("الاستجابة غير موجودة.", 404, "response_not_found")
        prior_review = session.scalar(select(ResponseReview).where(ResponseReview.response_id == response_id))
        if prior_review is not None:
            raise ServiceError("سبق اتخاذ قرار نهائي بشأن هذه الاستجابة.", 409, "response_already_reviewed")
        if response.status != "hold":
            raise ServiceError("لا يمكن مراجعة استجابة ليست معلّقة.", 409, "response_not_held")

        if decision == "accept":
            accepted_count = session.scalar(
                select(func.count()).select_from(SurveyResponse).where(
                    SurveyResponse.survey_id == campaign.id,
                    SurveyResponse.survey_version_id == response.survey_version_id,
                    SurveyResponse.status.in_(tuple(ACCEPTED_STATUSES)),
                )
            ) or 0
            if accepted_count >= campaign.response_limit:
                raise ServiceError("اكتملت الحصة الإجمالية؛ لا يمكن قبول استجابة إضافية.", 409, "campaign_full")

            version = session.get(SurveyVersion, response.survey_version_id)
            try:
                schema = survey_from_dict(json.loads(version.schema_json)) if version else None
                answers = json.loads(response.answers_json)
            except (ValueError, TypeError, json.JSONDecodeError):
                schema, answers = None, {}
            if schema is None:
                raise ServiceError("تعذر التحقق من إصدار الاستبيان؛ لا يمكن قبول الاستجابة.", 409, "survey_version_missing")

            accepted_rows = list(session.scalars(
                select(SurveyResponse).where(
                    SurveyResponse.survey_id == campaign.id,
                    SurveyResponse.survey_version_id == response.survey_version_id,
                    SurveyResponse.status.in_(tuple(ACCEPTED_STATUSES)),
                )
            ))
            for question_id, caps in schema.quotas.items():
                answer = answers.get(question_id)
                cap = caps.get(answer) if answer is not None else None
                if cap is None:
                    continue
                count = sum(
                    1 for row in accepted_rows
                    if json.loads(row.answers_json).get(question_id) == answer
                )
                if count >= cap:
                    raise ServiceError("اكتملت الحصة الخاصة بهذه الفئة؛ يلزم إبقاء القرار معلقاً أو تطبيق سياسة الدراسة.", 409, "quota_cell_full")

            amount = campaign.reward_per_response_dzd
            if amount > 0:
                available = session.scalar(
                    select(func.coalesce(func.sum(RewardLedgerEntry.available_delta_dzd), 0))
                    .where(RewardLedgerEntry.survey_id == campaign.id)
                ) or 0
                if available < amount:
                    raise ServiceError("رصيد المكافآت غير كافٍ؛ لن يُقبل الرد قبل استعادة تغطية التمويل.", 409, "reward_funding_invariant_failed")
                obligation = RewardObligation(
                    id=uuid.uuid4().hex, survey_id=campaign.id, response_id=response.id,
                    participant_id=response.participant_id, amount_dzd=amount, status="pending",
                )
                session.add(obligation)
                session.add(RewardLedgerEntry(
                    id=uuid.uuid4().hex, survey_id=campaign.id, response_id=response.id,
                    event_type="reward_reserved", idempotency_key=f"reserve:{response.id}",
                    amount_dzd=amount, available_delta_dzd=-amount, obligated_delta_dzd=amount,
                    paid_delta_dzd=0, reference=f"response:{response.id}", actor_user_id=reviewer_id,
                ))
            response.status = "accepted_flagged"
        session.add(ResponseReview(
            id=uuid.uuid4().hex,
            response_id=response.id,
            reviewer_user_id=reviewer_id,
            decision=decision,
            reason_code=reason_code,
            note=note,
        ))
        _audit(session, reviewer_id, f"response.review.{decision}", "response", response.id, {
            "decision": decision,
            "reason_code": reason_code,
            "note_length": len(note),
            "reward_reserved": bool(decision == "accept" and campaign.reward_per_response_dzd > 0),
        })
        session.flush()
        return {"response_id": response.id, "decision": decision,
                "status": response.status if decision == "accept" else "review_rejected"}


def response_review_counts(session_factory: sessionmaker, survey_id: str) -> dict[str, int]:
    with session_factory() as session:
        rows = session.scalars(select(ResponseReview.decision).join(SurveyResponse).where(
            SurveyResponse.survey_id == survey_id,
        ))
        counts = {"accept": 0, "reject": 0}
        for decision in rows:
            counts[decision] = counts.get(decision, 0) + 1
        return counts
