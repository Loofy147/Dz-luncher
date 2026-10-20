from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

from app.models import AuthSession, User

SESSION_COOKIE = "dz_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 14


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class SessionIdentity:
    user_id: str
    role: str
    display_name: str
    email: str
    csrf_token: str
    session_token: str


def session_secret() -> bytes:
    configured = os.getenv("SESSION_SECRET")
    if configured:
        secret = configured.encode("utf-8")
        if len(secret) < 32:
            raise RuntimeError("SESSION_SECRET must contain at least 32 bytes")
        return secret
    if os.getenv("APP_ENV", "development").lower() == "production":
        raise RuntimeError("SESSION_SECRET is required in production")
    return b"development-only-change-me-before-deployment-32bytes!"


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 10 or len(password) > 256:
        raise ValueError("يجب أن تتكوّن كلمة المرور من 10 أحرف على الأقل")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = encoded.split("$", 2)
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def sign_session_token(token: str, secret: bytes | None = None) -> str:
    key = secret or session_secret()
    signature = hmac.new(key, token.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{token}.{signature}"


def verify_session_cookie(cookie_value: str | None, secret: bytes | None = None) -> str | None:
    if not cookie_value or "." not in cookie_value:
        return None
    token, signature = cookie_value.rsplit(".", 1)
    if not token or len(token) > 100:
        return None
    expected = hmac.new(secret or session_secret(), token.encode("ascii", "ignore"), hashlib.sha256).hexdigest()
    return token if hmac.compare_digest(signature, expected) else None


def create_session(session_factory: sessionmaker, user: User) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    with session_factory() as session, session.begin():
        session.add(AuthSession(
            token_hash=_token_hash(token), user_id=user.id, csrf_token=csrf,
            expires_at=int(time.time()) + SESSION_TTL_SECONDS,
        ))
    return sign_session_token(token), csrf


def load_identity(session_factory: sessionmaker, cookie_value: str | None) -> SessionIdentity | None:
    token = verify_session_cookie(cookie_value)
    if token is None:
        return None
    with session_factory() as session:
        auth_session = session.get(AuthSession, _token_hash(token))
        if auth_session is None or auth_session.expires_at < int(time.time()):
            if auth_session is not None:
                session.delete(auth_session)
                session.commit()
            return None
        user = session.get(User, auth_session.user_id)
        if user is None:
            return None
        return SessionIdentity(
            user_id=user.id, role=user.role, display_name=user.display_name, email=user.email,
            csrf_token=auth_session.csrf_token, session_token=token,
        )


def destroy_session(session_factory: sessionmaker, cookie_value: str | None) -> None:
    token = verify_session_cookie(cookie_value)
    if not token:
        return
    with session_factory() as session, session.begin():
        session.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))


def verify_csrf(identity: SessionIdentity, candidate: str | None) -> bool:
    return bool(candidate and hmac.compare_digest(identity.csrf_token, candidate))
