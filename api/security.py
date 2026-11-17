from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import Settings
from .errors import Unauthorized

_hasher = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2)


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return _hasher.verify(stored, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored)
    except InvalidHashError:
        return True


def token_fingerprint(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _encode(settings: Settings, payload: dict[str, Any], ttl_seconds: int) -> str:
    now = datetime.now(timezone.utc)
    body = {
        **payload,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "iss": "momenz",
    }
    return jwt.encode(body, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    settings: Settings, user_id: str, email: str, role: str
) -> tuple[str, int]:
    ttl = int(settings.access_token_ttl_minutes) * 60
    token = _encode(
        settings,
        {"sub": user_id, "email": email, "role": role, "type": "access"},
        ttl,
    )
    return token, ttl


def create_refresh_token(
    settings: Settings, user_id: str
) -> tuple[str, str, datetime]:
    """(ham token, D1'de saklanacak fingerprint, son geçerlilik) döndürür."""
    ttl = int(settings.refresh_token_ttl_days) * 86_400
    token_id = new_id()
    token = _encode(
        settings,
        {"sub": user_id, "jti": token_id, "type": "refresh"},
        ttl,
    )
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    return token, token_fingerprint(token), expires_at


def decode_token(
    settings: Settings, token: str, expected: Literal["access", "refresh"]
) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="momenz",
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise Unauthorized("Oturum geçersiz veya süresi dolmuş.") from exc
    if payload.get("type") != expected:
        raise Unauthorized("Token tipi beklenenle eşleşmiyor.")
    return payload
