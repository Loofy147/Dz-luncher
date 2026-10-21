"""Database-backed, fixed-window throttling for authentication endpoints.

Only HMAC fingerprints of the client identity are persisted. PostgreSQL and
SQLite use atomic UPSERTs, so counters are shared across app workers and survive
process restarts. This is an abuse-control layer, not a substitute for WAF/DDoS
protection.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import threading
import time
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker

from app.models import AuthRateLimitBucket
from app.security import session_secret
from app.services import ServiceError

AUTH_LIMITS: dict[str, tuple[int, int]] = {
    "login": (10, 15 * 60),
    "register": (5, 60 * 60),
    "forgot_password": (5, 60 * 60),
    "resend_verification": (3, 60 * 60),
    "reset_password": (10, 15 * 60),
    "verify_email": (20, 15 * 60),
}
BUCKET_RETENTION_SECONDS = 24 * 60 * 60
_PRUNE_EVERY = 256
_prune_counter = 0
_prune_lock = threading.Lock()


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    attempts: int
    retry_after: int


def _bucket_key(scope: str, key_material: str) -> str:
    message = b"dz-luncher/auth-rate-limit/v1\0" + scope.encode("utf-8") + b"\0" + key_material.encode("utf-8")
    return hmac.new(session_secret(), message, hashlib.sha256).hexdigest()


def _should_prune() -> bool:
    global _prune_counter
    with _prune_lock:
        _prune_counter += 1
        return _prune_counter % _PRUNE_EVERY == 0


def consume_rate_limit(
    session_factory: sessionmaker,
    *,
    scope: str,
    key_material: str,
    limit: int,
    window_seconds: int,
    now: int | None = None,
) -> RateLimitDecision:
    """Atomically record one attempt in a fixed time window."""
    if not isinstance(scope, str) or not scope or len(scope) > 80:
        raise ValueError("rate_limit_scope_invalid")
    if not isinstance(key_material, str) or not key_material or len(key_material) > 256:
        raise ValueError("rate_limit_key_invalid")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("rate_limit_limit_must_be_positive")
    if isinstance(window_seconds, bool) or not isinstance(window_seconds, int) or window_seconds < 1:
        raise ValueError("rate_limit_window_must_be_positive")

    now_seconds = int(time.time()) if now is None else now
    if isinstance(now_seconds, bool) or not isinstance(now_seconds, int) or now_seconds < 0:
        raise ValueError("rate_limit_time_invalid")
    window_start = now_seconds - (now_seconds % window_seconds)
    bucket_key = _bucket_key(scope, key_material)
    table = AuthRateLimitBucket.__table__

    with session_factory() as session, session.begin():
        dialect = session.get_bind().dialect.name
        values = {
            "bucket_key": bucket_key,
            "window_start": window_start,
            "hits": 1,
            "updated_at": now_seconds,
        }
        if dialect == "postgresql":
            statement = postgresql_insert(table).values(**values)
        elif dialect == "sqlite":
            statement = sqlite_insert(table).values(**values)
        else:
            raise RuntimeError(f"Unsupported database dialect for atomic rate limits: {dialect}")

        statement = statement.on_conflict_do_update(
            index_elements=[table.c.bucket_key],
            set_={
                "window_start": window_start,
                "hits": case(
                    (table.c.window_start == window_start, table.c.hits + 1),
                    else_=1,
                ),
                "updated_at": now_seconds,
            },
        )
        # Return the hit count written by this UPSERT itself, rather than
        # issuing a second SELECT under concurrent traffic.
        attempts = session.scalar(statement.returning(table.c.hits))
        if attempts is None:
            raise RuntimeError("rate_limit_bucket_write_missing")
        if _should_prune():
            session.execute(delete(AuthRateLimitBucket).where(
                AuthRateLimitBucket.updated_at < now_seconds - BUCKET_RETENTION_SECONDS
            ))

    retry_after = max(1, window_start + window_seconds - now_seconds)
    return RateLimitDecision(
        allowed=attempts <= limit,
        limit=limit,
        attempts=attempts,
        retry_after=retry_after,
    )


def _client_key(request: Request) -> str:
    """Use forwarded identity only when the immediate peer is in an explicit trust CIDR."""
    peer = request.client.host if request.client and request.client.host else "unknown"
    header_name = os.getenv("RATE_LIMIT_TRUSTED_CLIENT_IP_HEADER", "").strip().lower()
    if header_name not in {"x-real-ip", "cf-connecting-ip"}:
        return str(peer)[:128]

    raw_cidrs = os.getenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "").strip()
    if not raw_cidrs:
        return str(peer)[:128]
    try:
        networks = [
            ipaddress.ip_network(item.strip(), strict=False)
            for item in raw_cidrs.split(",")
            if item.strip()
        ]
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        # Invalid or ambiguous trust configuration must not grant trust to a proxy.
        return str(peer)[:128]
    if not networks or not any(peer_ip.version == network.version and peer_ip in network for network in networks):
        return str(peer)[:128]

    candidate = request.headers.get(header_name, "").strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return str(peer)[:128]


RATE_LIMIT_POLICIES: dict[str, tuple[int, int]] = {
    **{f"auth:{action}": policy for action, policy in AUTH_LIMITS.items()},
    # Submission endpoints need both network-level and account/campaign-level controls.
    "request:survey_response_ip": (60, 60 * 60),
    "request:survey_response_user": (10, 60 * 60),
}


def enforce_rate_limit(
    request: Request,
    scope: str,
    *,
    key_material: str | None = None,
) -> None:
    """Apply a named persisted policy; callers may provide a scoped account key."""
    policy = RATE_LIMIT_POLICIES.get(scope)
    if policy is None:
        raise ValueError("unsupported_rate_limit_scope")
    limit, window_seconds = policy
    material = _client_key(request) if key_material is None else key_material
    decision = consume_rate_limit(
        request.app.state.session_factory,
        scope=scope,
        key_material=material,
        limit=limit,
        window_seconds=window_seconds,
    )
    if not decision.allowed:
        raise ServiceError(
            "تم تجاوز عدد المحاولات المسموح به. حاول مرة أخرى بعد انتهاء المهلة.",
            429,
            "rate_limit_exceeded",
            headers={"Retry-After": str(decision.retry_after)},
        )


def enforce_auth_rate_limit(request: Request, action: str) -> None:
    if action not in AUTH_LIMITS:
        raise ValueError("unsupported_auth_rate_limit_action")
    enforce_rate_limit(request, f"auth:{action}")
