"""Safe account verification and password-reset token lifecycle."""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from app.models import AuditEvent, AuthActionToken, AuthSession, User
from app.security import hash_password

EMAIL_VERIFICATION_TTL_SECONDS = 24 * 60 * 60
PASSWORD_RESET_TTL_SECONDS = 30 * 60
TOKEN_RESEND_COOLDOWN_SECONDS = 60
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{40,100}$")
_PURPOSES = {"verify_email", "reset_password"}


def email_verification_required() -> bool:
    """Never permit an environment flag to turn verification off in production."""
    import os

    if os.getenv("APP_ENV", "development").lower() == "production":
        return True
    return os.getenv("EMAIL_VERIFICATION_REQUIRED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("ascii")).hexdigest()


def issue_auth_action_token(
    session_factory: sessionmaker,
    *,
    user_id: str,
    purpose: str,
    ttl_seconds: int,
) -> str | None:
    """Issue one opaque token; only its digest is stored. Enforce per-user cooldown."""
    if purpose not in _PURPOSES:
        raise ValueError("unsupported_auth_action_purpose")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds < 1:
        raise ValueError("ttl_seconds_must_be_positive")
    now = int(time.time())
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)

    with session_factory() as session, session.begin():
        user = session.get(User, user_id)
        if user is None:
            return None
        if purpose == "verify_email" and user.email_verified_at is not None:
            return None
        recent = session.scalar(
            select(AuthActionToken.token_hash)
            .where(
                AuthActionToken.user_id == user_id,
                AuthActionToken.purpose == purpose,
                AuthActionToken.created_at > now - TOKEN_RESEND_COOLDOWN_SECONDS,
            )
            .limit(1)
        )
        if recent is not None:
            return None
        session.execute(
            delete(AuthActionToken).where(
                AuthActionToken.user_id == user_id,
                AuthActionToken.purpose == purpose,
            )
        )
        session.add(AuthActionToken(
            token_hash=token_hash,
            user_id=user_id,
            purpose=purpose,
            expires_at=now + ttl_seconds,
            created_at=now,
        ))
        session.add(AuditEvent(
            id=secrets.token_hex(16),
            actor_user_id=user_id,
            event_type=f"auth.{purpose}.issued",
            target_type="user",
            target_id=user_id,
            details_json="{}",
        ))
    return raw_token


def _find_valid_token(session, raw_token: str, purpose: str, now: int) -> AuthActionToken | None:
    if not isinstance(raw_token, str) or not _TOKEN_RE.fullmatch(raw_token) or purpose not in _PURPOSES:
        return None
    row = session.scalar(
        select(AuthActionToken)
        .where(
            AuthActionToken.token_hash == _hash_token(raw_token),
            AuthActionToken.purpose == purpose,
            AuthActionToken.expires_at > now,
        )
        .with_for_update()
    )
    return row


def verify_email_token(session_factory: sessionmaker, raw_token: str) -> bool:
    now = int(time.time())
    with session_factory() as session, session.begin():
        token = _find_valid_token(session, raw_token, "verify_email", now)
        if token is None:
            return False
        user = session.get(User, token.user_id)
        if user is None:
            session.delete(token)
            return False
        if user.email_verified_at is None:
            user.email_verified_at = datetime.now(timezone.utc)
            session.add(AuditEvent(
                id=secrets.token_hex(16),
                actor_user_id=user.id,
                event_type="auth.email_verified",
                target_type="user",
                target_id=user.id,
                details_json="{}",
            ))
        session.execute(
            delete(AuthActionToken).where(
                AuthActionToken.user_id == user.id,
                AuthActionToken.purpose == "verify_email",
            )
        )
    return True


def reset_password_with_token(session_factory: sessionmaker, raw_token: str, new_password: str) -> bool:
    # Avoid expensive password hashing for random/invalid tokens, then re-check under lock.
    now = int(time.time())
    with session_factory() as session:
        token = _find_valid_token(session, raw_token, "reset_password", now)
        if token is None:
            return False
        user_id = token.user_id
    password_digest = hash_password(new_password)

    with session_factory() as session, session.begin():
        token = _find_valid_token(session, raw_token, "reset_password", int(time.time()))
        if token is None or token.user_id != user_id:
            return False
        user = session.get(User, user_id)
        if user is None:
            session.delete(token)
            return False
        user.password_hash = password_digest
        session.execute(
            delete(AuthActionToken).where(
                AuthActionToken.user_id == user.id,
                AuthActionToken.purpose == "reset_password",
            )
        )
        # A password reset must revoke every session, not only the browser doing it.
        session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        session.add(AuditEvent(
            id=secrets.token_hex(16),
            actor_user_id=user.id,
            event_type="auth.password_reset",
            target_type="user",
            target_id=user.id,
            details_json="{}",
        ))
    return True
