"""Private durable in-app notifications."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import AuditEvent, Notification


def add_notification(
    session,
    *,
    user_id: str,
    event_type: str,
    title: str,
    body: str,
    target_path: str = "/",
) -> Notification:
    """Queue a private, non-email notification in the caller's transaction."""
    if not isinstance(event_type, str) or not event_type.strip() or len(event_type) > 80:
        raise ValueError("invalid_notification_event_type")
    if not isinstance(title, str) or not title.strip() or len(title) > 180:
        raise ValueError("invalid_notification_title")
    if not isinstance(body, str) or not body.strip() or len(body) > 1000:
        raise ValueError("invalid_notification_body")
    if (
        not isinstance(target_path, str)
        or len(target_path) > 300
        or not target_path.startswith("/")
        or target_path.startswith("//")
        or "://" in target_path
        or "\r" in target_path
        or "\n" in target_path
    ):
        raise ValueError("notification_target_must_be_a_local_path")
    notification = Notification(
        id=uuid.uuid4().hex,
        user_id=user_id,
        event_type=event_type,
        title=title.strip(),
        body=body.strip(),
        target_path=target_path,
    )
    session.add(notification)
    return notification


def list_user_notifications(
    session_factory: sessionmaker,
    *,
    user_id: str,
    limit: int = 100,
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("notification_limit_must_be_between_1_and_500")
    with session_factory() as session:
        rows = list(session.scalars(
            select(Notification).where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id)
            .limit(limit)
        ))
        unread_count = session.scalar(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
        ) or 0
        return {
            "items": [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "title": row.title,
                    "body": row.body,
                    "target_path": row.target_path,
                    "created_at": row.created_at,
                    "read_at": row.read_at,
                    "is_read": row.read_at is not None,
                }
                for row in rows
            ],
            "unread_count": unread_count,
        }


def mark_notification_read(
    session_factory: sessionmaker,
    *,
    notification_id: str,
    user_id: str,
) -> None:
    with session_factory() as session, session.begin():
        notification = session.scalar(
            select(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .with_for_update()
        )
        if notification is None:
            raise LookupError("notification_not_found")
        if notification.read_at is None:
            notification.read_at = datetime.now(timezone.utc)
            session.add(AuditEvent(
                id=secrets.token_hex(16),
                actor_user_id=user_id,
                event_type="notification.marked_read",
                target_type="notification",
                target_id=notification.id,
                details_json="{}",
            ))
