"""Privacy-rights request intake and audited operator triage."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import DataSubjectRequest, User
from app.services import ServiceError, _audit

REQUEST_TYPES = {
    "access": "الوصول إلى البيانات",
    "correction": "تصحيح البيانات",
    "deletion": "طلب الحذف",
    "objection": "الاعتراض على معالجة",
    "other": "طلب خصوصية آخر",
}
REQUEST_STATUSES = {
    "open": "مفتوح",
    "in_review": "قيد المراجعة",
    "needs_information": "يحتاج معلومات إضافية",
    "completed": "مكتمل",
    "rejected": "مرفوض مع توضيح السبب",
}
TERMINAL_STATUSES = {"completed", "rejected"}
ALLOWED_TRANSITIONS = {
    "open": {"in_review", "needs_information", "completed", "rejected"},
    "in_review": {"open", "needs_information", "completed", "rejected"},
    "needs_information": {"open", "in_review", "completed", "rejected"},
}


def _request_dict(row: DataSubjectRequest, requester_email: str = "") -> dict[str, Any]:
    return {
        "id": row.id,
        "request_type": row.request_type,
        "request_type_label": REQUEST_TYPES[row.request_type],
        "details": row.details,
        "status": row.status,
        "status_label": REQUEST_STATUSES[row.status],
        "resolution_note": row.resolution_note,
        "requester_email": requester_email,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "closed_at": row.closed_at,
        "handled_by_user_id": row.handled_by_user_id,
    }


def create_privacy_request(
    session_factory: sessionmaker,
    *,
    requester_id: str,
    request_type: str,
    details: str,
) -> dict[str, Any]:
    if request_type not in REQUEST_TYPES:
        raise ServiceError("نوع طلب الخصوصية غير صالح.", 422, "invalid_privacy_request_type")
    if not isinstance(details, str):
        raise ServiceError("نص الطلب غير صالح.", 422, "invalid_privacy_request_details")
    details = details.strip()
    if len(details) > 2000:
        raise ServiceError("تفاصيل الطلب يجب ألا تتجاوز 2000 حرف.", 422, "privacy_request_details_too_long")

    request_id = uuid.uuid4().hex
    with session_factory() as session, session.begin():
        requester = session.get(User, requester_id)
        if requester is None:
            raise ServiceError("الحساب غير موجود.", 404, "requester_not_found")
        row = DataSubjectRequest(
            id=request_id,
            user_id=requester_id,
            request_type=request_type,
            details=details,
            status="open",
            resolution_note="",
        )
        session.add(row)
        session.flush()
        # Audit metadata intentionally excludes free-text request details.
        _audit(session, requester_id, "privacy_request.created", "privacy_request", row.id, {
            "request_type": request_type,
        })
    return {
        "id": request_id,
        "request_type": request_type,
        "request_type_label": REQUEST_TYPES[request_type],
        "details": details,
        "status": "open",
        "status_label": REQUEST_STATUSES["open"],
        "resolution_note": "",
        "requester_email": "",
    }


def list_privacy_requests(
    session_factory: sessionmaker,
    *,
    requester_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("privacy_request_limit_must_be_between_1_and_500")
    with session_factory() as session:
        query = select(DataSubjectRequest)
        if requester_id is not None:
            query = query.where(DataSubjectRequest.user_id == requester_id)
        rows = list(session.scalars(query.order_by(DataSubjectRequest.created_at.desc(), DataSubjectRequest.id).limit(limit)))
        output = []
        for row in rows:
            requester = session.get(User, row.user_id) if row.user_id else None
            output.append(_request_dict(row, requester.email if requester else ""))
        return output


def update_privacy_request(
    session_factory: sessionmaker,
    *,
    request_id: str,
    actor_user_id: str,
    new_status: str,
    resolution_note: str,
) -> dict[str, Any]:
    if new_status not in REQUEST_STATUSES:
        raise ServiceError("حالة طلب الخصوصية غير صالحة.", 422, "invalid_privacy_request_status")
    if not isinstance(resolution_note, str):
        raise ServiceError("ملاحظة المعالجة غير صالحة.", 422, "invalid_resolution_note")
    note = resolution_note.strip()
    if len(note) > 2000:
        raise ServiceError("ملاحظة المعالجة يجب ألا تتجاوز 2000 حرف.", 422, "resolution_note_too_long")
    if (new_status in TERMINAL_STATUSES or new_status == "needs_information") and len(note) < 10:
        raise ServiceError("اكتب ملاحظة واضحة من 10 أحرف على الأقل لهذه الحالة.", 422, "resolution_note_required")

    with session_factory() as session, session.begin():
        actor = session.get(User, actor_user_id)
        if actor is None or actor.role != "admin":
            raise ServiceError("هذه العملية تتطلب صلاحية مشغّل مخوّل.", 403, "admin_required")
        row = session.scalar(
            select(DataSubjectRequest)
            .where(DataSubjectRequest.id == request_id)
            .with_for_update()
        )
        if row is None:
            raise ServiceError("طلب الخصوصية غير موجود.", 404, "privacy_request_not_found")
        if row.status in TERMINAL_STATUSES:
            raise ServiceError("الطلب مغلق؛ لا يمكن تغيير حالته النهائية.", 409, "privacy_request_terminal")
        if new_status != row.status and new_status not in ALLOWED_TRANSITIONS[row.status]:
            raise ServiceError("انتقال الحالة غير مسموح.", 409, "invalid_privacy_request_transition")
        if new_status == row.status and note == row.resolution_note:
            return _request_dict(row)

        old_status = row.status
        row.status = new_status
        if note:
            row.resolution_note = note
        row.handled_by_user_id = actor_user_id
        row.updated_at = datetime.now(timezone.utc)
        row.closed_at = datetime.now(timezone.utc) if new_status in TERMINAL_STATUSES else None
        _audit(session, actor_user_id, "privacy_request.status_changed", "privacy_request", row.id, {
            "from_status": old_status,
            "to_status": new_status,
            "resolution_note_length": len(note),
        })
        session.flush()
        requester = session.get(User, row.user_id) if row.user_id else None
        return _request_dict(row, requester.email if requester else "")
