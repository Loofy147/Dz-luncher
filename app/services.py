from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import (
    AuditEvent, RewardLedgerEntry, RewardObligation, ResponseAppeal, ResponseReview, SurveyCampaign,
    SurveyResponse, SurveyVersion, User,
)
from app.security import hash_password, verify_password
from app.notifications import add_notification
from validation_core import (
    ACCEPTED_STATUSES, Hypothesis, ProcessedResponse, Response,
    build_report, process_responses, pseudo_id, response_from_dict, survey_from_dict,
)


class ServiceError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str = "invalid_request",
        headers: Mapping[str, str] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.headers = dict(headers or {})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _pseudonym_secret() -> bytes:
    configured = os.getenv("PSEUDONYM_SECRET")
    if configured:
        key = configured.encode("utf-8")
        if len(key) < 32:
            raise RuntimeError("PSEUDONYM_SECRET must contain at least 32 bytes")
        return key
    if os.getenv("APP_ENV", "development").lower() == "production":
        raise RuntimeError("PSEUDONYM_SECRET is required in production")
    return b"development-only-pseudonym-secret-replace-before-release-0001"


def _audit(session, actor_id: str | None, event: str, target_type: str, target_id: str, details: Mapping[str, Any] | None = None) -> None:
    session.add(AuditEvent(
        id=uuid.uuid4().hex, actor_user_id=actor_id, event_type=event,
        target_type=target_type, target_id=target_id, details_json=_dump(dict(details or {})),
    ))


def register_user(session_factory: sessionmaker, *, email: str, password: str, display_name: str, role: str) -> User:
    email = email.strip().lower()
    display_name = display_name.strip()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ServiceError("أدخل بريداً إلكترونياً صالحاً.", 422, "invalid_email")
    if not display_name or len(display_name) > 100:
        raise ServiceError("الاسم مطلوب ويجب ألا يتجاوز 100 حرف.", 422, "invalid_display_name")
    if role not in {"business", "participant"}:
        raise ServiceError("نوع الحساب غير صالح.", 422, "invalid_role")
    password_digest = hash_password(password)
    user = User(id=uuid.uuid4().hex, email=email, display_name=display_name, password_hash=password_digest, role=role)
    try:
        with session_factory() as session, session.begin():
            session.add(user)
            session.flush()
            _audit(session, user.id, "account.registered", "user", user.id, {"role": role})
        return user
    except IntegrityError as exc:
        raise ServiceError("هذا البريد الإلكتروني مستخدم بالفعل.", 409, "email_exists") from exc


def authenticate_user(session_factory: sessionmaker, *, email: str, password: str) -> User:
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None or not verify_password(password, user.password_hash):
            # Same message for unknown email and wrong password.
            raise ServiceError("البريد الإلكتروني أو كلمة المرور غير صحيحة.", 401, "invalid_credentials")
        return user


def _parse_hypotheses(items: Any) -> tuple[Hypothesis, ...]:
    if not isinstance(items, list):
        raise ServiceError("يجب أن تكون الفرضيات قائمة JSON.", 422, "invalid_hypotheses")
    if len(items) > 30:
        raise ServiceError("الحد الأقصى 30 فرضية لكل استبيان.", 422, "too_many_hypotheses")
    hypotheses: list[Hypothesis] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ServiceError(f"الفرضية {index + 1} يجب أن تكون كائناً.", 422, "invalid_hypothesis")
        allowed = {"id", "question_id", "positive_values", "threshold", "minimum_n", "evidence_type", "segment_question_id", "segment_option_id"}
        unknown = set(item) - allowed
        if unknown:
            raise ServiceError(f"حقول غير معروفة في الفرضية: {', '.join(sorted(unknown))}", 422, "unknown_hypothesis_fields")

        hypothesis_id = item.get("id")
        question_id = item.get("question_id")
        values = item.get("positive_values")
        threshold = item.get("threshold")
        minimum_n = item.get("minimum_n")
        evidence_type = item.get("evidence_type", "declared")
        segment_question_id = item.get("segment_question_id")
        segment_option_id = item.get("segment_option_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id.strip() or len(hypothesis_id) > 100:
            raise ServiceError(f"معرّف الفرضية {index + 1} غير صالح.", 422, "invalid_hypothesis")
        if not isinstance(question_id, str) or not question_id.strip():
            raise ServiceError(f"يجب تحديد السؤال الذي تقيسه الفرضية {index + 1}.", 422, "invalid_hypothesis")
        if not isinstance(values, list) or not values:
            raise ServiceError(f"يجب تحديد قائمة قيم موجبة غير فارغة للفرضية {hypothesis_id}.", 422, "invalid_hypothesis_values")
        if any(isinstance(value, bool) or not isinstance(value, (str, int, float)) for value in values):
            raise ServiceError(f"القيم الموجبة للفرضية {hypothesis_id} يجب أن تكون نصوصاً أو أعداداً.", 422, "invalid_hypothesis_values")
        if len(set(values)) != len(values):
            raise ServiceError(f"تحتوي الفرضية {hypothesis_id} على قيم موجبة مكررة.", 422, "invalid_hypothesis_values")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ServiceError(f"حد الفرضية {hypothesis_id} يجب أن يكون رقماً بين 0 و1.", 422, "invalid_hypothesis")
        try:
            threshold_value = float(threshold)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ServiceError(f"حد الفرضية {hypothesis_id} غير صالح.", 422, "invalid_hypothesis") from exc
        if not math.isfinite(threshold_value) or not 0 <= threshold_value <= 1:
            raise ServiceError(f"حد الفرضية {hypothesis_id} يجب أن يكون بين 0 و1.", 422, "invalid_hypothesis")
        if isinstance(minimum_n, bool) or not isinstance(minimum_n, int) or minimum_n < 1:
            raise ServiceError(f"الحد الأدنى للعينة في الفرضية {hypothesis_id} يجب أن يكون عدداً صحيحاً موجباً.", 422, "invalid_hypothesis")
        if evidence_type != "declared":
            raise ServiceError("الفرضيات المعتمدة على الإجابات تبدأ كدليل مُصرّح به فقط.", 422, "unsupported_evidence_type")
        if segment_question_id is not None and (not isinstance(segment_question_id, str) or not segment_question_id.strip()):
            raise ServiceError(f"سؤال التقسيم في الفرضية {hypothesis_id} غير صالح.", 422, "invalid_hypothesis")
        if segment_option_id is not None and (not isinstance(segment_option_id, str) or not segment_option_id.strip()):
            raise ServiceError(f"خيار التقسيم في الفرضية {hypothesis_id} غير صالح.", 422, "invalid_hypothesis")
        if (segment_question_id is None) != (segment_option_id is None):
            raise ServiceError(f"تحديد الشريحة في الفرضية {hypothesis_id} يتطلب السؤال والخيار معاً.", 422, "invalid_hypothesis")
        hypotheses.append(Hypothesis(
            id=hypothesis_id, question_id=question_id, positive_values=tuple(values),
            threshold=threshold_value, minimum_n=minimum_n, evidence_type=evidence_type,
            segment_question_id=segment_question_id, segment_option_id=segment_option_id,
        ))
    return tuple(hypotheses)


def _validate_hypotheses(schema, hypotheses: Sequence[Hypothesis]) -> None:
    try:
        build_report([], schema, hypotheses)
    except ValueError as exc:
        raise ServiceError(f"عقد الفرضيات غير صالح: {exc}", 422, "invalid_hypotheses") from exc

    question_by_id = {question.id: question for question in schema.questions}
    for hypothesis in hypotheses:
        question = question_by_id[hypothesis.question_id]
        if question.kind == "single":
            valid_options = {option.id for option in question.options}
            if any(not isinstance(value, str) or value not in valid_options for value in hypothesis.positive_values):
                raise ServiceError(
                    f"تحتوي الفرضية {hypothesis.id} على خيار غير موجود في السؤال {question.id}.",
                    422, "invalid_hypothesis_values",
                )
        elif question.kind in {"scale", "number"}:
            for value in hypothesis.positive_values:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ServiceError(
                        f"القيم الموجبة للفرضية {hypothesis.id} يجب أن تطابق النوع الرقمي للسؤال {question.id}.",
                        422, "invalid_hypothesis_values",
                    )
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ServiceError(f"قيمة غير صالحة في الفرضية {hypothesis.id}.", 422, "invalid_hypothesis_values") from exc
                if not math.isfinite(numeric_value) or numeric_value < question.lo or numeric_value > question.hi:
                    raise ServiceError(
                        f"قيمة الفرضية {hypothesis.id} خارج نطاق السؤال {question.id}.",
                        422, "invalid_hypothesis_values",
                    )
                if question.kind == "scale" and not numeric_value.is_integer():
                    raise ServiceError(
                        f"قيمة الفرضية {hypothesis.id} غير قابلة للاختيار في مقياس السؤال {question.id}.",
                        422, "invalid_hypothesis_values",
                    )
        else:
            raise ServiceError(
                f"لا تدعم فرضية القرار السؤال النصي المفتوح {question.id} مباشرة؛ صنّف الإجابات بمراجعة مستقلة أولاً.",
                422, "unsupported_hypothesis_question_type",
            )


def _validate_campaign_input(payload: Mapping[str, Any], campaign_id: str, *, draft_version: str) -> tuple[str, str, str, int, int, dict, list]:
    allowed_fields = {"title", "objective", "description", "reward_per_response_dzd", "response_limit", "questions", "quotas", "hypotheses"}
    unknown_fields = set(payload) - allowed_fields
    if unknown_fields:
        raise ServiceError(f"حقول غير معروفة في بيانات الدراسة: {', '.join(sorted(unknown_fields))}", 422, "unknown_campaign_fields")
    title = str(payload.get("title", "")).strip()
    objective = str(payload.get("objective", "")).strip()
    description = str(payload.get("description", "")).strip()
    if not title or len(title) > 180:
        raise ServiceError("عنوان الاستبيان مطلوب (180 حرفاً كحد أقصى).", 422, "invalid_title")
    if not objective or len(objective) > 1000:
        raise ServiceError("حدّد القرار الذي تريد التحقق منه (1000 حرف كحد أقصى).", 422, "invalid_objective")
    if len(description) > 4000:
        raise ServiceError("الوصف يتجاوز 4000 حرف.", 422, "description_too_long")
    try:
        reward = int(payload.get("reward_per_response_dzd", 0))
        response_limit = int(payload.get("response_limit", 100))
    except (TypeError, ValueError) as exc:
        raise ServiceError("المكافأة والحد الأقصى يجب أن يكونا أعداداً صحيحة بالدينار الجزائري.", 422, "invalid_reward_or_limit") from exc
    if reward < 0 or reward > 100_000:
        raise ServiceError("المكافأة لكل مشاركة يجب أن تكون بين 0 و100000 دج.", 422, "invalid_reward")
    if not 1 <= response_limit <= 5000:
        raise ServiceError("عدد المشاركات يجب أن يكون بين 1 و5000.", 422, "invalid_response_limit")

    questions = payload.get("questions")
    quotas = payload.get("quotas", {})
    hypotheses_data = payload.get("hypotheses", [])
    contract = {"project_id": campaign_id, "version_id": draft_version, "questions": questions, "quotas": quotas}
    try:
        schema = survey_from_dict(contract)
    except (ValueError, TypeError) as exc:
        raise ServiceError(f"بنية الاستبيان غير صالحة: {exc}", 422, "invalid_survey_schema") from exc
    hypotheses = _parse_hypotheses(hypotheses_data)
    _validate_hypotheses(schema, hypotheses)
    return title, objective, description, reward, response_limit, contract, hypotheses_data


def create_draft(session_factory: sessionmaker, owner_id: str, payload: Mapping[str, Any]) -> SurveyCampaign:
    campaign_id = uuid.uuid4().hex
    slug = "s-" + secrets.token_hex(6)
    values = _validate_campaign_input(payload, campaign_id, draft_version="draft-v1")
    title, objective, description, reward, limit, schema, hypotheses = values
    with session_factory() as session, session.begin():
        owner = session.get(User, owner_id)
        if owner is None or owner.role not in {"business", "admin"}:
            raise ServiceError("إنشاء الاستبيانات متاح لحسابات أصحاب المشاريع.", 403, "business_role_required")
        campaign = SurveyCampaign(
            id=campaign_id, slug=slug, owner_id=owner_id, title=title, objective=objective,
            description=description, reward_per_response_dzd=reward, response_limit=limit,
            status="draft", version_number=0, current_version_id=None,
            draft_schema_json=_dump(schema), hypotheses_json=_dump(hypotheses),
        )
        session.add(campaign)
        session.flush()
        _audit(session, owner_id, "survey.draft_created", "survey", campaign.id, {"slug": slug, "question_count": len(schema["questions"])})
    return campaign


def update_draft(session_factory: sessionmaker, owner_id: str, slug: str, payload: Mapping[str, Any]) -> SurveyCampaign:
    with session_factory() as session:
        campaign = session.scalar(select(SurveyCampaign).where(SurveyCampaign.slug == slug))
        if campaign is None:
            raise ServiceError("الاستبيان غير موجود.", 404, "survey_not_found")
        campaign_id = campaign.id
        current_status = campaign.status
    if current_status != "draft":
        raise ServiceError("النسخة المنشورة ثابتة. أنشئ إصداراً جديداً قبل تعديل الأسئلة.", 409, "published_version_immutable")
    values = _validate_campaign_input(payload, campaign_id, draft_version="draft-v1")
    title, objective, description, reward, limit, schema, hypotheses = values
    with session_factory() as session, session.begin():
        campaign = session.scalar(select(SurveyCampaign).where(SurveyCampaign.slug == slug).with_for_update())
        if campaign is None:
            raise ServiceError("الاستبيان غير موجود.", 404, "survey_not_found")
        if campaign.owner_id != owner_id:
            raise ServiceError("لا تملك صلاحية تعديل هذا الاستبيان.", 403, "owner_required")
        if campaign.status != "draft":
            raise ServiceError("النسخة المنشورة ثابتة. أنشئ إصداراً جديداً قبل تعديل الأسئلة.", 409, "published_version_immutable")
        campaign.title, campaign.objective, campaign.description = title, objective, description
        campaign.reward_per_response_dzd, campaign.response_limit = reward, limit
        campaign.draft_schema_json, campaign.hypotheses_json = _dump(schema), _dump(hypotheses)
        _audit(session, owner_id, "survey.draft_updated", "survey", campaign.id, {"question_count": len(schema["questions"])})
    return campaign


def publish_campaign(session_factory: sessionmaker, owner_id: str, slug: str) -> tuple[SurveyCampaign, SurveyVersion]:
    with session_factory() as session, session.begin():
        campaign = session.scalar(select(SurveyCampaign).where(SurveyCampaign.slug == slug).with_for_update())
        if campaign is None:
            raise ServiceError("الاستبيان غير موجود.", 404, "survey_not_found")
        if campaign.owner_id != owner_id:
            raise ServiceError("لا تملك صلاحية نشر هذا الاستبيان.", 403, "owner_required")
        if campaign.status != "draft":
            raise ServiceError("يمكن نشر المسودة مرة واحدة في هذا الإصدار. إدارة الإصدارات الجديدة ستضاف لاحقاً.", 409, "survey_not_draft")
        schema_data = _load(campaign.draft_schema_json, {})
        version_id = "v-" + uuid.uuid4().hex
        schema_data["project_id"] = campaign.id
        schema_data["version_id"] = version_id
        try:
            schema = survey_from_dict(schema_data)
        except (ValueError, TypeError) as exc:
            raise ServiceError(f"تعذر التحقق من الاستبيان: {exc}", 422, "invalid_survey_schema") from exc
        hypotheses = _parse_hypotheses(_load(campaign.hypotheses_json, []))
        _validate_hypotheses(schema, hypotheses)
        available = session.scalar(select(func.coalesce(func.sum(RewardLedgerEntry.available_delta_dzd), 0)).where(RewardLedgerEntry.survey_id == campaign.id)) or 0
        required_funding = campaign.reward_per_response_dzd * campaign.response_limit
        if available < required_funding:
            raise ServiceError(
                f"النشر يتطلب تمويلاً مؤكداً يغطي الحد الأقصى للحملة: {required_funding:,} دج. الرصيد المتاح {available:,} دج.",
                409, "insufficient_campaign_funding",
            )
        next_version = campaign.version_number + 1
        version = SurveyVersion(
            version_id=version_id, survey_id=campaign.id, version_number=next_version,
            schema_json=_dump(schema_data), hypotheses_json=campaign.hypotheses_json,
        )
        session.add(version)
        session.flush()
        campaign.version_number = next_version
        campaign.current_version_id = version_id
        campaign.status = "published"
        campaign.published_at = _now()
        _audit(session, owner_id, "survey.published", "survey", campaign.id, {"version_id": version_id, "response_limit": campaign.response_limit, "reward_per_response_dzd": campaign.reward_per_response_dzd})
    return campaign, version


def _campaign_by_slug(session, slug: str, *, lock: bool = False) -> SurveyCampaign:
    query = select(SurveyCampaign).where(SurveyCampaign.slug == slug)
    if lock:
        query = query.with_for_update()
    campaign = session.scalar(query)
    if campaign is None:
        raise ServiceError("الاستبيان غير موجود.", 404, "survey_not_found")
    return campaign


def public_campaigns(session_factory: sessionmaker) -> list[dict[str, Any]]:
    with session_factory() as session:
        campaigns = list(session.scalars(select(SurveyCampaign).where(SurveyCampaign.status == "published").order_by(SurveyCampaign.published_at.desc())))
        output = []
        for campaign in campaigns:
            accepted_n = session.scalar(select(func.count()).select_from(SurveyResponse).where(
                SurveyResponse.survey_id == campaign.id, SurveyResponse.survey_version_id == campaign.current_version_id,
                SurveyResponse.status.in_(tuple(ACCEPTED_STATUSES)),
            )) or 0
            if accepted_n >= campaign.response_limit:
                continue
            output.append({
                "id": campaign.id, "slug": campaign.slug, "title": campaign.title,
                "objective": campaign.objective, "description": campaign.description,
                "reward_per_response_dzd": campaign.reward_per_response_dzd,
                "response_limit": campaign.response_limit, "accepted_n": accepted_n,
                "remaining": campaign.response_limit - accepted_n, "version_id": campaign.current_version_id,
            })
        return output


def get_public_campaign(session_factory: sessionmaker, slug: str) -> tuple[SurveyCampaign, SurveyVersion, dict]:
    with session_factory() as session:
        campaign = _campaign_by_slug(session, slug)
        if campaign.status != "published" or not campaign.current_version_id:
            raise ServiceError("هذا الاستبيان غير منشور حالياً.", 404, "survey_not_published")
        version = session.get(SurveyVersion, campaign.current_version_id)
        if version is None:
            raise ServiceError("إصدار الاستبيان غير متاح.", 500, "survey_version_missing")
        schema = _load(version.schema_json, {})
        accepted_n = session.scalar(select(func.count()).select_from(SurveyResponse).where(
            SurveyResponse.survey_id == campaign.id, SurveyResponse.survey_version_id == version.version_id,
            SurveyResponse.status.in_(tuple(ACCEPTED_STATUSES)),
        )) or 0
        summary = {"accepted_n": accepted_n, "remaining": max(0, campaign.response_limit - accepted_n)}
        return campaign, version, {"schema": schema, **summary}


def submit_response(
    session_factory: sessionmaker, *, slug: str, participant_id: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    allowed = {"submission_id", "survey_version_id", "seconds", "answers"}
    unknown = set(payload) - allowed
    if unknown:
        raise ServiceError(f"حقول غير معروفة: {', '.join(sorted(unknown))}", 422, "unknown_response_fields")
    submission_id = payload.get("submission_id")
    version_id = payload.get("survey_version_id")
    answers = payload.get("answers")
    seconds = payload.get("seconds", 0)
    if not isinstance(submission_id, str) or not 1 <= len(submission_id) <= 100:
        raise ServiceError("معرّف الإرسال غير صالح.", 422, "invalid_submission_id")
    if not isinstance(version_id, str) or not isinstance(answers, dict):
        raise ServiceError("بيانات الإجابة أو إصدار الاستبيان غير صالحة.", 422, "invalid_response_payload")
    try:
        seconds_value = float(seconds)
        if not (0 <= seconds_value <= 86_400):
            raise ValueError
        seconds_int = int(seconds_value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ServiceError("زمن الإجابة غير صالح.", 422, "invalid_elapsed_seconds") from exc
    fingerprint_data = {"participant_id": participant_id, "survey_version_id": version_id, "seconds": seconds_int, "answers": answers}
    payload_hash = hashlib.sha256(_dump(fingerprint_data).encode("utf-8")).hexdigest()

    with session_factory() as session, session.begin():
        campaign = _campaign_by_slug(session, slug, lock=True)
        if campaign.status != "published" or not campaign.current_version_id:
            raise ServiceError("الحملة غير مفتوحة للمشاركة.", 409, "survey_not_open")
        existing_submission = session.scalar(select(SurveyResponse).where(
            SurveyResponse.survey_id == campaign.id, SurveyResponse.submission_id == submission_id,
        ))
        if existing_submission is not None:
            if existing_submission.payload_hash != payload_hash:
                raise ServiceError("استُخدم معرّف الإرسال نفسه مع إجابات مختلفة.", 409, "idempotency_conflict")
            obligation = session.scalar(select(RewardObligation).where(RewardObligation.response_id == existing_submission.id))
            return {"response_id": existing_submission.id, "status": existing_submission.status, "idempotent_replay": True,
                    "reward_status": obligation.status if obligation else "not_earned", "reward_amount_dzd": obligation.amount_dzd if obligation else 0}
        if version_id != campaign.current_version_id:
            raise ServiceError("إصدار الاستبيان تغيّر؛ أعد فتح النموذج قبل الإرسال.", 409, "survey_version_mismatch")
        prior = session.scalar(select(SurveyResponse).where(
            SurveyResponse.survey_id == campaign.id, SurveyResponse.participant_id == participant_id,
            SurveyResponse.status.in_(("accepted", "accepted_flagged", "hold", "screened_out", "quota_full", "excluded_duplicate")),
        ))
        if prior is not None:
            duplicate = SurveyResponse(
                id=uuid.uuid4().hex, survey_id=campaign.id, survey_version_id=version_id,
                submission_id=submission_id, participant_id=participant_id, payload_hash=payload_hash,
                answers_json="{}", status="excluded_duplicate", signals_json='["duplicate_submission"]',
                review_groups_json='[]', errors_json='[]', pseudonym=pseudo_id(participant_id, _pseudonym_secret(), campaign.id),
                elapsed_seconds=seconds_int,
            )
            session.add(duplicate)
            session.flush()
            _audit(session, None, "response.duplicate_excluded", "response", duplicate.id, {"survey_id": campaign.id})
            add_notification(
                session, user_id=participant_id, event_type="response.excluded_duplicate",
                title="لم تُحتسب المشاركة المكررة",
                body="سُجلت هذه المحاولة كمكررة. راجع سجل ردودك لمعرفة حالة الاستجابة السابقة.",
                target_path="/my-responses",
            )
            return {"response_id": duplicate.id, "status": duplicate.status, "idempotent_replay": False, "reward_status": "not_earned", "reward_amount_dzd": 0}

        accepted_count = session.scalar(select(func.count()).select_from(SurveyResponse).where(
            SurveyResponse.survey_id == campaign.id, SurveyResponse.survey_version_id == version_id,
            SurveyResponse.status.in_(tuple(ACCEPTED_STATUSES)),
        )) or 0
        if accepted_count >= campaign.response_limit:
            raise ServiceError("اكتمل عدد المشاركات لهذه الحملة.", 409, "campaign_full")

        version = session.get(SurveyVersion, version_id)
        if version is None:
            raise ServiceError("إصدار الاستبيان غير موجود.", 500, "survey_version_missing")
        schema_json = _load(version.schema_json, {})
        try:
            survey = survey_from_dict(schema_json)
            candidate = response_from_dict({
                "submission_id": submission_id, "participant_id": participant_id,
                "device_id": None, "seconds": seconds_int, "answers": answers,
                "survey_version_id": version_id,
            })
        except (ValueError, TypeError) as exc:
            raise ServiceError(f"تعذر قراءة الاستبيان أو الإجابة: {exc}", 422, "invalid_response_contract") from exc

        accepted_history = list(session.scalars(select(SurveyResponse).where(
            SurveyResponse.survey_id == campaign.id, SurveyResponse.survey_version_id == version_id,
            SurveyResponse.status.in_(tuple(ACCEPTED_STATUSES)),
        ).order_by(SurveyResponse.submitted_at.asc())))
        history: list[Response] = []
        for item in accepted_history:
            history.append(Response(
                submission_id=item.submission_id, participant_id=item.participant_id, device_id=None,
                seconds=item.elapsed_seconds or 0, answers=_load(item.answers_json, {}), survey_version_id=version_id,
            ))
        processed, _ = process_responses(survey, history + [candidate], _pseudonym_secret())
        evaluated: ProcessedResponse = processed[-1]
        status = evaluated.status
        if status not in {"invalid", "screened_out"}:
            # The transactional database, not a batch simulation, is authoritative
            # for quota counts and the campaign-wide completion cap.
            quota_full = False
            for question_id, caps in survey.quotas.items():
                answer = evaluated.normalized_answers.get(question_id)
                cap = caps.get(answer)
                if cap is None:
                    continue
                matching = 0
                for accepted_item in accepted_history:
                    old_answers = _load(accepted_item.answers_json, {})
                    if old_answers.get(question_id) == answer:
                        matching += 1
                if matching >= cap:
                    quota_full = True
                    break
            if len(accepted_history) >= campaign.response_limit:
                raise ServiceError("اكتمل عدد المشاركات لهذه الحملة.", 409, "campaign_full")
            if len(evaluated.review_groups) >= 2:
                status = "hold"
            elif quota_full:
                status = "quota_full"
            elif evaluated.review_groups:
                status = "accepted_flagged"
            else:
                status = "accepted"

        stored_answers = evaluated.normalized_answers if status in {"accepted", "accepted_flagged", "hold"} else {}
        record = SurveyResponse(
            id=uuid.uuid4().hex, survey_id=campaign.id, survey_version_id=version_id,
            submission_id=submission_id, participant_id=participant_id, payload_hash=payload_hash,
            answers_json=_dump(stored_answers), status=status, signals_json=_dump(list(evaluated.signals)),
            review_groups_json=_dump(list(evaluated.review_groups)), errors_json=_dump(list(evaluated.errors)),
            pseudonym=pseudo_id(participant_id, _pseudonym_secret(), campaign.id), elapsed_seconds=seconds_int,
        )
        session.add(record)
        session.flush()

        reward_status = "not_earned"
        reward_amount = 0
        if status in ACCEPTED_STATUSES and campaign.reward_per_response_dzd > 0:
            available = session.scalar(select(func.coalesce(func.sum(RewardLedgerEntry.available_delta_dzd), 0)).where(RewardLedgerEntry.survey_id == campaign.id)) or 0
            amount = campaign.reward_per_response_dzd
            if available < amount:
                raise ServiceError("توقّف إصدار المكافأة لأن الرصيد المموّل غير كافٍ؛ أُلغيت العملية كاملة.", 409, "reward_funding_invariant_failed")
            obligation = RewardObligation(
                id=uuid.uuid4().hex, survey_id=campaign.id, response_id=record.id,
                participant_id=participant_id, amount_dzd=amount, status="pending",
            )
            session.add(obligation)
            session.add(RewardLedgerEntry(
                id=uuid.uuid4().hex, survey_id=campaign.id, response_id=record.id,
                event_type="reward_reserved", idempotency_key=f"reserve:{record.id}", amount_dzd=amount,
                available_delta_dzd=-amount, obligated_delta_dzd=amount, paid_delta_dzd=0,
                reference=f"response:{record.id}", actor_user_id=None,
            ))
            reward_status, reward_amount = "pending", amount
        _audit(session, participant_id, "response.submitted", "response", record.id, {"survey_id": campaign.id, "status": status, "reward_status": reward_status})
        notification_messages = {
            "accepted": ("استجابتك مقبولة", "تم قبول الاستجابة. راجع سجل ردودك وسجل المكافآت عند انطباق الشروط."),
            "accepted_flagged": ("استجابتك مقبولة بعد فحص الجودة", "قُبلت الاستجابة مع إشارة جودة للمراجعة التحليلية؛ لا يعني ذلك رفضاً."),
            "hold": ("استجابتك قيد المراجعة", "وصلت الاستجابة إلى مراجعة بشرية. الإشارات الآلية ليست حكماً نهائياً، وستظهر الحالة هنا."),
            "screened_out": ("انتهى التأهيل لهذه الدراسة", "لم تنطبق معايير التأهيل المعلنة على هذه المشاركة."),
            "invalid": ("تعذر قبول الإجابة", "لم تُقبل الإجابة بسبب خطأ في البيانات. راجع سجل ردودك وتعليمات الدراسة."),
            "quota_full": ("اكتملت حصة الفئة", "اكتملت الحصة المحددة لهذه الفئة؛ لم تُحتسب الإجابة كمشاركة مقبولة."),
            "excluded_duplicate": ("لم تُحتسب المشاركة المكررة", "يُسمح بمشاركة واحدة فقط في الدراسة؛ راجع حالة الاستجابة السابقة."),
        }
        notification_title, notification_body = notification_messages.get(
            status, ("تم تحديث حالة الاستجابة", "راجع سجل ردودك للاطلاع على الحالة الحالية."),
        )
        add_notification(
            session, user_id=participant_id, event_type=f"response.{status}",
            title=notification_title, body=notification_body, target_path="/my-responses",
        )
        return {"response_id": record.id, "status": status, "idempotent_replay": False, "reward_status": reward_status, "reward_amount_dzd": reward_amount}


def _ledger_totals(session, survey_id: str) -> dict[str, int]:
    entries = session.scalars(select(RewardLedgerEntry).where(RewardLedgerEntry.survey_id == survey_id))
    totals = {"available_dzd": 0, "obligated_dzd": 0, "paid_dzd": 0, "entry_count": 0}
    for entry in entries:
        totals["available_dzd"] += entry.available_delta_dzd
        totals["obligated_dzd"] += entry.obligated_delta_dzd
        totals["paid_dzd"] += entry.paid_delta_dzd
        totals["entry_count"] += 1
    return totals


def fund_campaign(session_factory: sessionmaker, *, slug_or_id: str, amount_dzd: int, reference: str, idempotency_key: str, actor_user_id: str | None = None, operator_label: str | None = None) -> dict[str, Any]:
    if isinstance(amount_dzd, bool) or not isinstance(amount_dzd, int) or amount_dzd <= 0:
        raise ServiceError("مبلغ التمويل يجب أن يكون عدداً صحيحاً موجباً بالدينار.", 422, "invalid_funding_amount")
    if not reference.strip() or len(reference) > 200:
        raise ServiceError("مرجع إثبات التمويل مطلوب.", 422, "funding_reference_required")
    if not idempotency_key.strip() or len(idempotency_key) > 160:
        raise ServiceError("مفتاح تكرار التمويل غير صالح.", 422, "invalid_idempotency_key")
    with session_factory() as session, session.begin():
        campaign = session.scalar(select(SurveyCampaign).where((SurveyCampaign.slug == slug_or_id) | (SurveyCampaign.id == slug_or_id)).with_for_update())
        if campaign is None:
            raise ServiceError("الحملة غير موجودة.", 404, "survey_not_found")
        existing = session.scalar(select(RewardLedgerEntry).where(RewardLedgerEntry.idempotency_key == idempotency_key))
        if existing is not None:
            if existing.survey_id != campaign.id or existing.event_type != "funding" or existing.amount_dzd != amount_dzd or existing.reference != reference:
                raise ServiceError("مفتاح التمويل مستخدم في عملية مختلفة.", 409, "funding_idempotency_conflict")
            return {**_ledger_totals(session, campaign.id), "idempotent_replay": True}
        session.add(RewardLedgerEntry(
            id=uuid.uuid4().hex, survey_id=campaign.id, event_type="funding", idempotency_key=idempotency_key,
            amount_dzd=amount_dzd, available_delta_dzd=amount_dzd, obligated_delta_dzd=0, paid_delta_dzd=0,
            reference=reference, actor_user_id=actor_user_id,
        ))
        _audit(session, actor_user_id, "reward.funding_recorded", "survey", campaign.id, {"amount_dzd": amount_dzd, "reference": reference, "operator_label": (operator_label or "").strip()[:120]})
        session.flush()
        return {**_ledger_totals(session, campaign.id), "idempotent_replay": False}


def mark_reward_paid(session_factory: sessionmaker, *, obligation_id: str, reference: str, actor_user_id: str | None = None, operator_label: str | None = None) -> dict[str, Any]:
    if not reference.strip() or len(reference) > 200:
        raise ServiceError("مرجع الدفع الفعلي مطلوب.", 422, "payment_reference_required")
    with session_factory() as session, session.begin():
        obligation = session.scalar(select(RewardObligation).where(RewardObligation.id == obligation_id).with_for_update())
        if obligation is None:
            raise ServiceError("استحقاق المكافأة غير موجود.", 404, "reward_not_found")
        if obligation.status == "paid":
            if obligation.payment_reference == reference:
                return {"obligation_id": obligation.id, "status": "paid", "idempotent_replay": True}
            raise ServiceError("سبق تسوية هذه المكافأة بمرجع مختلف.", 409, "reward_already_paid")
        if obligation.status != "pending":
            raise ServiceError("حالة الاستحقاق لا تسمح بالتسوية.", 409, "reward_not_payable")
        key = f"paid:{obligation.id}"
        existing = session.scalar(select(RewardLedgerEntry).where(RewardLedgerEntry.idempotency_key == key))
        if existing is not None:
            raise ServiceError("تعارض في سجل التسوية؛ يلزم فحص الدفتر.", 409, "ledger_invariant_conflict")
        session.add(RewardLedgerEntry(
            id=uuid.uuid4().hex, survey_id=obligation.survey_id, response_id=obligation.response_id,
            event_type="reward_paid", idempotency_key=key, amount_dzd=obligation.amount_dzd,
            available_delta_dzd=0, obligated_delta_dzd=-obligation.amount_dzd, paid_delta_dzd=obligation.amount_dzd,
            reference=reference, actor_user_id=actor_user_id,
        ))
        obligation.status = "paid"
        obligation.payment_reference = reference
        obligation.paid_at = _now()
        add_notification(
            session, user_id=obligation.participant_id, event_type="reward.paid",
            title="تمت مطابقة تسوية المكافأة",
            body="سُجلت التسوية بموجب مرجع خارجي من المشغّل. راجع سجل المكافآت للتفاصيل.",
            target_path="/rewards",
        )
        _audit(session, actor_user_id, "reward.marked_paid", "reward", obligation.id, {"reference": reference, "amount_dzd": obligation.amount_dzd, "operator_label": (operator_label or "").strip()[:120]})
        session.flush()
        return {"obligation_id": obligation.id, "status": "paid", "idempotent_replay": False}


def campaign_report(session_factory: sessionmaker, *, slug: str, owner_id: str) -> dict[str, Any]:
    with session_factory() as session:
        campaign = _campaign_by_slug(session, slug)
        if campaign.owner_id != owner_id:
            raise ServiceError("التقرير متاح لصاحب الاستبيان فقط.", 403, "owner_required")
        if not campaign.current_version_id:
            raise ServiceError("انشر الاستبيان قبل طلب التقرير.", 409, "survey_not_published")
        version = session.get(SurveyVersion, campaign.current_version_id)
        if version is None:
            raise ServiceError("إصدار التقرير غير موجود.", 500, "survey_version_missing")
        survey = survey_from_dict(_load(version.schema_json, {}))
        persisted = list(session.scalars(select(SurveyResponse).where(
            SurveyResponse.survey_id == campaign.id, SurveyResponse.survey_version_id == version.version_id,
        ).order_by(SurveyResponse.submitted_at.asc())))
        rows: list[ProcessedResponse] = []
        reviews = list(session.scalars(select(ResponseReview).where(
            ResponseReview.response_id.in_([item.id for item in persisted])
        ))) if persisted else []
        review_by_response = {review.response_id: review for review in reviews}
        appeals = list(session.scalars(select(ResponseAppeal).where(
            ResponseAppeal.response_id.in_([item.id for item in persisted])
        ))) if persisted else []
        appeal_by_response = {appeal.response_id: appeal for appeal in appeals}
        for item in persisted:
            response = Response(
                submission_id=item.submission_id, participant_id=item.participant_id, device_id=None,
                seconds=item.elapsed_seconds or 0, answers=_load(item.answers_json, {}), survey_version_id=version.version_id,
            )
            review = review_by_response.get(item.id)
            appeal = appeal_by_response.get(item.id)
            report_status = item.status
            if item.status == "hold" and review and review.decision == "reject":
                report_status = "appeal_pending" if appeal and appeal.status in {"open", "in_review"} else "review_rejected"
            rows.append(ProcessedResponse(
                response=response, status=report_status, signals=tuple(_load(item.signals_json, [])),
                review_groups=tuple(_load(item.review_groups_json, [])), errors=tuple(_load(item.errors_json, [])),
                normalized_answers=_load(item.answers_json, {}),
            ))
        hypotheses = _parse_hypotheses(_load(version.hypotheses_json, []))
        report = build_report(rows, survey, hypotheses)
        distributions: dict[str, list[dict[str, Any]]] = {}
        accepted_rows = [r for r in rows if r.status in ACCEPTED_STATUSES]
        for question in survey.questions:
            counts = Counter(r.normalized_answers[question.id] for r in accepted_rows if question.id in r.normalized_answers)
            if question.kind == "single":
                labels = {option.id: option.label for option in question.options}
                distributions[question.id] = [
                    {"value": value, "label": labels.get(value, str(value)), "count": count,
                     "share": count / sum(counts.values()) if counts else 0.0}
                    for value, count in counts.most_common()
                ]
            elif question.kind in {"number", "scale"}:
                distributions[question.id] = [
                    {"value": value, "label": str(value), "count": count,
                     "share": count / sum(counts.values()) if counts else 0.0}
                    for value, count in sorted(counts.items(), key=lambda pair: float(pair[0]))
                ]
        totals = _ledger_totals(session, campaign.id)
        pending_rewards = session.scalar(select(func.count()).select_from(RewardObligation).where(
            RewardObligation.survey_id == campaign.id, RewardObligation.status == "pending",
        )) or 0
        return {
            "survey": {"id": campaign.id, "slug": campaign.slug, "title": campaign.title,
                       "status": campaign.status, "response_limit": campaign.response_limit,
                       "reward_per_response_dzd": campaign.reward_per_response_dzd, "version_id": version.version_id},
            "sample_flow": report["sample_flow"], "accepted_n": report["accepted_n"],
            "hypotheses": report["hypotheses"], "limitations": report["limitations"],
            "distributions": distributions, "question_labels": {question.id: question.text for question in survey.questions},
            "reward_ledger": totals, "pending_rewards": pending_rewards,
        }


def business_campaigns(session_factory: sessionmaker, owner_id: str) -> list[dict[str, Any]]:
    with session_factory() as session:
        campaigns = list(session.scalars(select(SurveyCampaign).where(SurveyCampaign.owner_id == owner_id).order_by(SurveyCampaign.created_at.desc())))
        result = []
        for campaign in campaigns:
            accepted_n = session.scalar(select(func.count()).select_from(SurveyResponse).where(
                SurveyResponse.survey_id == campaign.id, SurveyResponse.status.in_(tuple(ACCEPTED_STATUSES)),
            )) or 0
            ledger = _ledger_totals(session, campaign.id)
            result.append({"id": campaign.id, "slug": campaign.slug, "title": campaign.title,
                           "objective": campaign.objective, "status": campaign.status,
                           "accepted_n": accepted_n, "response_limit": campaign.response_limit,
                           "reward_per_response_dzd": campaign.reward_per_response_dzd, **ledger})
        return result


def participant_rewards(session_factory: sessionmaker, participant_id: str) -> list[dict[str, Any]]:
    with session_factory() as session:
        obligations = session.scalars(select(RewardObligation).where(RewardObligation.participant_id == participant_id).order_by(RewardObligation.created_at.desc()))
        output = []
        for item in obligations:
            campaign = session.get(SurveyCampaign, item.survey_id)
            output.append({"id": item.id, "survey_title": campaign.title if campaign else "استبيان",
                           "amount_dzd": item.amount_dzd, "status": item.status, "reference": item.payment_reference})
        return output


def response_status_counts(session_factory: sessionmaker, slug: str, owner_id: str) -> dict[str, int]:
    with session_factory() as session:
        campaign = _campaign_by_slug(session, slug)
        if campaign.owner_id != owner_id:
            raise ServiceError("لا تملك صلاحية الاطلاع على هذه النتائج.", 403, "owner_required")
        rows = list(session.scalars(select(SurveyResponse).where(SurveyResponse.survey_id == campaign.id)))
        reviews = list(session.scalars(select(ResponseReview).join(SurveyResponse).where(
            SurveyResponse.survey_id == campaign.id,
        )))
        rejected_ids = {review.response_id for review in reviews if review.decision == "reject"}
        appeals = list(session.scalars(select(ResponseAppeal).join(SurveyResponse).where(
            SurveyResponse.survey_id == campaign.id,
        )))
        appeal_by_response = {appeal.response_id: appeal for appeal in appeals}
        counts = Counter()
        for row in rows:
            appeal = appeal_by_response.get(row.id)
            if row.status == "hold" and row.id in rejected_ids:
                status = "appeal_pending" if appeal and appeal.status in {"open", "in_review"} else "review_rejected"
            else:
                status = row.status
            counts[status] += 1
        return {status: counts.get(status, 0) for status in (
            "accepted", "accepted_flagged", "hold", "appeal_pending", "review_rejected",
            "screened_out", "invalid", "quota_full", "excluded_duplicate",
        )}
