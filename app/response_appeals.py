"""Participant response history, appeals, and second-level adjudication."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import (
    RewardLedgerEntry, RewardObligation, ResponseAppeal,
    ResponseReview, SurveyCampaign, SurveyResponse, SurveyVersion, User,
)
from app.notifications import add_notification
from app.services import ServiceError, _audit
from validation_core import ACCEPTED_STATUSES, survey_from_dict

APPEAL_STATUSES = {
    "open": "اعتراض قيد المراجعة",
    "in_review": "الاعتراض قيد الدراسة",
    "upheld": "تثبيت قرار الرفض بعد الاعتراض",
    "overturned": "إلغاء الرفض وقبول الاستجابة",
}
APPEAL_TERMINAL_STATUSES = {"upheld", "overturned"}


def _load_json(text: str, fallback: Any) -> Any:
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _answer_items(schema_json: str, answers_json: str) -> list[dict[str, str]]:
    try:
        schema = survey_from_dict(_load_json(schema_json, {}))
        answers = _load_json(answers_json, {})
    except (ValueError, TypeError):
        return []
    if not isinstance(answers, dict):
        return []
    items: list[dict[str, str]] = []
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
        items.append({"question": question.text, "answer": rendered, "kind": question.kind})
    return items


def list_participant_responses(
    session_factory: sessionmaker, *, participant_id: str, limit: int = 200,
) -> list[dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("participant_response_limit_must_be_between_1_and_500")
    with session_factory() as session:
        responses = list(session.scalars(
            select(SurveyResponse)
            .where(SurveyResponse.participant_id == participant_id)
            .order_by(SurveyResponse.submitted_at.desc(), SurveyResponse.id)
            .limit(limit)
        ))
        if not responses:
            return []
        response_ids = [response.id for response in responses]
        review_by_response = {
            review.response_id: review
            for review in session.scalars(select(ResponseReview).where(ResponseReview.response_id.in_(response_ids)))
        }
        appeal_by_response = {
            appeal.response_id: appeal
            for appeal in session.scalars(select(ResponseAppeal).where(ResponseAppeal.response_id.in_(response_ids)))
        }
        labels = {
            "accepted": "مقبولة",
            "accepted_flagged": "مقبولة بعد المراجعة",
            "hold": "قيد المراجعة البشرية",
            "screened_out": "غير مطابقة لشروط التأهيل",
            "invalid": "بيانات غير صالحة",
            "quota_full": "اكتملت الحصة",
            "excluded_duplicate": "استجابة مكررة مستبعدة",
        }
        output: list[dict[str, Any]] = []
        for response in responses:
            campaign = session.get(SurveyCampaign, response.survey_id)
            review = review_by_response.get(response.id)
            appeal = appeal_by_response.get(response.id)
            status = response.status
            can_appeal = bool(response.status == "hold" and review and review.decision == "reject" and appeal is None)
            if response.status == "hold" and review and review.decision == "reject":
                if appeal is None:
                    status, status_label = "review_rejected", "مرفوضة بعد المراجعة — يمكنك الاعتراض"
                elif appeal.status in {"open", "in_review"}:
                    status, status_label = "appeal_pending", APPEAL_STATUSES[appeal.status]
                elif appeal.status == "upheld":
                    status, status_label = "review_rejected", APPEAL_STATUSES["upheld"]
                else:
                    status, status_label = "accepted_flagged", APPEAL_STATUSES["overturned"]
            else:
                status_label = labels.get(status, "حالة غير معروفة")
            output.append({
                "response_id": response.id,
                "survey_title": campaign.title if campaign else "استبيان",
                "survey_slug": campaign.slug if campaign else "",
                "status": status,
                "status_label": status_label,
                "submitted_at": response.submitted_at,
                "signals": _load_json(response.signals_json, []),
                "appeal_status": appeal.status if appeal else None,
                "appeal_status_label": APPEAL_STATUSES.get(appeal.status, "") if appeal else "",
                "appeal_resolution_note": appeal.resolution_note if appeal else "",
                "can_appeal": can_appeal,
            })
        return output


def create_response_appeal(
    session_factory: sessionmaker,
    *,
    participant_id: str,
    response_id: str,
    reason: str,
) -> dict[str, Any]:
    if not isinstance(reason, str):
        raise ServiceError("نص الاعتراض غير صالح.", 422, "invalid_appeal_reason")
    reason = reason.strip()
    if len(reason) < 10 or len(reason) > 2000:
        raise ServiceError("يجب أن يتراوح سبب الاعتراض بين 10 و2000 حرف.", 422, "invalid_appeal_reason")

    appeal_id = uuid.uuid4().hex
    with session_factory() as session, session.begin():
        response = session.scalar(
            select(SurveyResponse).where(SurveyResponse.id == response_id).with_for_update()
        )
        if response is None or response.participant_id != participant_id:
            # Do not reveal whether another participant's response exists.
            raise ServiceError("الاستجابة غير موجودة أو لا تملك صلاحية الاعتراض عليها.", 404, "response_not_found")
        review = session.scalar(select(ResponseReview).where(ResponseReview.response_id == response.id))
        if response.status != "hold" or review is None or review.decision != "reject":
            raise ServiceError("الاعتراض متاح فقط على قرار رفض نهائي بعد المراجعة البشرية.", 409, "response_not_appealable")
        existing = session.scalar(select(ResponseAppeal).where(ResponseAppeal.response_id == response.id))
        if existing is not None:
            raise ServiceError("سبق تسجيل اعتراض لهذه الاستجابة.", 409, "response_appeal_already_exists")

        appeal = ResponseAppeal(
            id=appeal_id,
            response_id=response.id,
            participant_id=participant_id,
            reason=reason,
            status="open",
            resolution_note="",
        )
        session.add(appeal)
        session.flush()
        _audit(session, participant_id, "response.appeal.created", "response_appeal", appeal.id, {
            "response_id": response.id,
            "reason_length": len(reason),
        })
        for admin_id in session.scalars(select(User.id).where(User.role == "admin")):
            add_notification(
                session, user_id=admin_id, event_type="response.appeal.submitted",
                title="اعتراض جديد ينتظر التحكيم",
                body="وصل اعتراض على قرار رفض سابق. راجعه من قائمة اعتراضات الاستجابات.",
                target_path="/admin/response-appeals",
            )
    return {"id": appeal_id, "response_id": response_id, "status": "open", "status_label": APPEAL_STATUSES["open"]}


def list_response_appeal_queue(
    session_factory: sessionmaker, *, limit: int = 100,
) -> list[dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("response_appeal_limit_must_be_between_1_and_500")
    with session_factory() as session:
        appeals = list(session.scalars(
            select(ResponseAppeal)
            .where(ResponseAppeal.status.in_(("open", "in_review")))
            .order_by(ResponseAppeal.created_at.asc(), ResponseAppeal.id)
            .limit(limit)
        ))
        output: list[dict[str, Any]] = []
        for appeal in appeals:
            response = session.get(SurveyResponse, appeal.response_id)
            campaign = session.get(SurveyCampaign, response.survey_id) if response else None
            review = session.scalar(select(ResponseReview).where(ResponseReview.response_id == appeal.response_id))
            version = session.get(SurveyVersion, response.survey_version_id) if response else None
            participant = session.get(User, appeal.participant_id)
            if response is None or campaign is None:
                continue
            output.append({
                "appeal_id": appeal.id,
                "response_id": response.id,
                "survey_id": campaign.id,
                "survey_title": campaign.title,
                "participant_pseudonym": response.pseudonym,
                "participant_email": participant.email if participant else "",
                "status": appeal.status,
                "status_label": APPEAL_STATUSES[appeal.status],
                "reason": appeal.reason,
                "created_at": appeal.created_at,
                "original_reason_code": review.reason_code if review else "unknown",
                "original_review_note": review.note if review else "",
                "answers": _answer_items(version.schema_json, response.answers_json) if version else [],
            })
        return output


def resolve_response_appeal(
    session_factory: sessionmaker,
    *,
    appeal_id: str,
    reviewer_id: str,
    decision: str,
    resolution_note: str,
) -> dict[str, Any]:
    if decision not in {"uphold", "overturn"}:
        raise ServiceError("قرار الاعتراض غير صالح.", 422, "invalid_response_appeal_decision")
    if not isinstance(resolution_note, str):
        raise ServiceError("ملاحظة حسم الاعتراض غير صالحة.", 422, "invalid_response_appeal_note")
    resolution_note = resolution_note.strip()
    if len(resolution_note) < 10 or len(resolution_note) > 2000:
        raise ServiceError("ملاحظة حسم الاعتراض يجب أن تتراوح بين 10 و2000 حرف.", 422, "invalid_response_appeal_note")

    with session_factory() as session:
        candidate = session.get(ResponseAppeal, appeal_id)
        if candidate is None:
            raise ServiceError("الاعتراض غير موجود.", 404, "response_appeal_not_found")
        candidate_response = session.get(SurveyResponse, candidate.response_id)
        if candidate_response is None:
            raise ServiceError("الاستجابة غير موجودة.", 404, "response_not_found")
        survey_id = candidate_response.survey_id
        response_id = candidate_response.id

    with session_factory() as session, session.begin():
        reviewer = session.get(User, reviewer_id)
        if reviewer is None or reviewer.role != "admin":
            raise ServiceError("هذه العملية تتطلب مشغّلاً مخوّلاً.", 403, "admin_required")
        campaign = session.scalar(select(SurveyCampaign).where(SurveyCampaign.id == survey_id).with_for_update())
        response = session.scalar(select(SurveyResponse).where(SurveyResponse.id == response_id).with_for_update())
        appeal = session.scalar(select(ResponseAppeal).where(ResponseAppeal.id == appeal_id).with_for_update())
        if campaign is None or response is None or appeal is None or appeal.response_id != response.id:
            raise ServiceError("الاعتراض غير موجود.", 404, "response_appeal_not_found")
        if appeal.status in APPEAL_TERMINAL_STATUSES:
            raise ServiceError("سبق حسم هذا الاعتراض؛ لا يمكن تغيير النتيجة النهائية.", 409, "response_appeal_already_resolved")
        if appeal.status not in {"open", "in_review"}:
            raise ServiceError("حالة الاعتراض لا تسمح بالحسم.", 409, "response_appeal_not_resolvable")
        if response.participant_id != appeal.participant_id:
            raise ServiceError("تعارض في ملكية الاستجابة والاعتراض.", 409, "response_appeal_invariant_conflict")
        original_review = session.scalar(select(ResponseReview).where(ResponseReview.response_id == response.id))
        if original_review is None or original_review.decision != "reject" or response.status != "hold":
            raise ServiceError("تعذر التحقق من قرار الرفض الأصلي.", 409, "response_appeal_invariant_conflict")

        reward_reserved = False
        if decision == "overturn":
            accepted_count = session.scalar(
                select(func.count()).select_from(SurveyResponse).where(
                    SurveyResponse.survey_id == campaign.id,
                    SurveyResponse.survey_version_id == response.survey_version_id,
                    SurveyResponse.status.in_(tuple(ACCEPTED_STATUSES)),
                )
            ) or 0
            if accepted_count >= campaign.response_limit:
                raise ServiceError("اكتملت الحصة الإجمالية؛ لا يمكن قبول الاستجابة بعد الاعتراض.", 409, "campaign_full")

            version = session.get(SurveyVersion, response.survey_version_id)
            try:
                schema = survey_from_dict(_load_json(version.schema_json, {})) if version else None
                answers = _load_json(response.answers_json, {})
            except (ValueError, TypeError):
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
                matching = 0
                for old_response in accepted_rows:
                    old_answers = _load_json(old_response.answers_json, {})
                    if old_answers.get(question_id) == answer:
                        matching += 1
                if matching >= cap:
                    raise ServiceError("اكتملت حصة هذه الفئة؛ لا يمكن قبول الاستجابة بعد الاعتراض.", 409, "quota_cell_full")

            amount = campaign.reward_per_response_dzd
            if amount > 0:
                idempotency_key = f"reserve:{response.id}"
                if session.scalar(select(RewardLedgerEntry).where(RewardLedgerEntry.idempotency_key == idempotency_key)) is not None:
                    raise ServiceError("تعارض في دفتر المكافآت؛ يلزم التحقق اليدوي.", 409, "ledger_invariant_conflict")
                available = session.scalar(
                    select(func.coalesce(func.sum(RewardLedgerEntry.available_delta_dzd), 0))
                    .where(RewardLedgerEntry.survey_id == campaign.id)
                ) or 0
                if available < amount:
                    raise ServiceError("الرصيد المموّل غير كافٍ؛ لم يُقبل الرد ولم تُحجز مكافأة.", 409, "reward_funding_invariant_failed")
                session.add(RewardObligation(
                    id=uuid.uuid4().hex, survey_id=campaign.id, response_id=response.id,
                    participant_id=response.participant_id, amount_dzd=amount, status="pending",
                ))
                session.add(RewardLedgerEntry(
                    id=uuid.uuid4().hex, survey_id=campaign.id, response_id=response.id,
                    event_type="reward_reserved", idempotency_key=idempotency_key,
                    amount_dzd=amount, available_delta_dzd=-amount, obligated_delta_dzd=amount,
                    paid_delta_dzd=0, reference=f"response:{response.id}", actor_user_id=reviewer_id,
                ))
                reward_reserved = True
            response.status = "accepted_flagged"
            appeal.status = "overturned"
        else:
            appeal.status = "upheld"

        now = datetime.now(timezone.utc)
        appeal.resolution_note = resolution_note
        appeal.handled_by_user_id = reviewer_id
        appeal.updated_at = now
        appeal.closed_at = now
        _audit(session, reviewer_id, f"response.appeal.{decision}", "response_appeal", appeal.id, {
            "response_id": response.id,
            "decision": decision,
            "resolution_note_length": len(resolution_note),
            "reward_reserved": reward_reserved,
        })
        if decision == "overturn":
            add_notification(
                session, user_id=response.participant_id, event_type="response.appeal.overturned",
                title="أُلغي رفض الاستجابة بعد الاعتراض",
                body="قبلت المراجعة الثانية الاستجابة. راجع سجل ردودك؛ إذا كانت الدراسة تقدم مكافأة فستظهر حالة الاستحقاق في سجل المكافآت.",
                target_path="/my-responses",
            )
        else:
            add_notification(
                session, user_id=response.participant_id, event_type="response.appeal.upheld",
                title="حُسم الاعتراض وبقي قرار الرفض",
                body="انتهت المراجعة الثانية إلى تثبيت القرار السابق. يمكنك مراجعة ملاحظة الحسم في سجل ردودك.",
                target_path="/my-responses",
            )
        session.flush()
        return {
            "appeal_id": appeal.id,
            "response_id": response.id,
            "decision": decision,
            "status": appeal.status,
            "reward_reserved": reward_reserved,
        }
