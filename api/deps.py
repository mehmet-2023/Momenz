from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request

from .config import Settings, get_settings
from .db import D1Client
from .errors import Forbidden, Unauthorized
from .ratelimit import InMemoryRateLimiter
from .repositories import users as user_repo
from .security import decode_token

_login_limiter = InMemoryRateLimiter(max_events=10, window_seconds=60.0)


@dataclass(slots=True)
class CurrentUser:
    id: str
    email: str
    role: str
    is_active: bool = True
    email_verified: bool = False


def get_db(request: Request) -> D1Client:
    client = getattr(request.app.state, "db", None)
    if client is None:
        raise RuntimeError("D1 istemci başlatılmadı.")
    return client


def _extract_token(request: Request, cookie_name: str) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.cookies.get(cookie_name)


def get_current_user(
    request: Request,
    settings: Settings = Depends(get_settings),
    db: D1Client = Depends(get_db),
) -> CurrentUser:
    token = _extract_token(request, settings.cookie_name)
    if not token:
        raise Unauthorized("Oturum bulunamadı. Lütfen giriş yap.")
    payload = decode_token(settings, token, "access")

    user_id = str(payload.get("sub") or "")
    if not user_id:
        raise Unauthorized("Oturum geçersiz.")

    cache: dict[str, tuple[float, CurrentUser | None]] = request.app.state.user_cache
    cached = cache.get(user_id)
    if cached and time.monotonic() - cached[0] < 30.0 and cached[1] is not None:
        return cached[1]

    row = user_repo.get_by_id(db, user_id)
    if not row or not int(row.get("is_active") or 0):
        cache.pop(user_id, None)
        raise Unauthorized("Hesap devre dışı bırakılmış.")

    user = CurrentUser(
        id=str(row["id"]),
        email=str(row["email"]),
        role=str(row.get("role") or "user"),
        is_active=bool(int(row.get("is_active") or 0)),
        email_verified=bool(int(row.get("email_verified") or 0)),
    )
    cache[user_id] = (time.monotonic(), user)
    return user


def require_user(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "admin":
        raise Forbidden("Bu işlem için yönetici yetkisi gerekiyor.")
    return user


def check_login_rate_limit(email: str, request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    if not _login_limiter.allows(f"{client_host}:{email.lower()}"):
        from .errors import RateLimited

        raise RateLimited()
