from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response

from ..config import Settings, get_settings
from ..cookies import clear_auth_cookies, set_auth_cookies
from ..db import D1Client
from ..deps import check_login_rate_limit, get_db, require_user
from ..schemas import (
    LoginIn,
    MessageOut,
    PasswordResetIn,
    RefreshIn,
    RegisterIn,
    TokenPair,
    UserOut,
)
from ..security import new_csrf_token
from ..services import auth as service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/csrf", response_model=dict)
def csrf(response: Response, settings: Settings = Depends(get_settings)) -> dict:
    token = new_csrf_token()
    response.set_cookie(
        settings.csrf_cookie_name,
        token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    return {"csrf_token": token}


@router.post("/register", response_model=MessageOut, status_code=201)
def register(
    payload: RegisterIn,
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageOut:
    return service.register(db, settings, payload)


@router.post("/login", response_model=TokenPair)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    check_login_rate_limit(str(payload.email), request)
    result = service.login(db, settings, payload)
    set_auth_cookies(
        response,
        settings,
        result.access_token,
        result.refresh_token,
        new_csrf_token(),
        settings.refresh_token_ttl_days * 86_400,
        settings.access_token_ttl_minutes * 60,
    )
    return result


@router.post("/refresh", response_model=TokenPair)
def refresh(
    request: Request,
    response: Response,
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
    payload: RefreshIn | None = None,
) -> TokenPair:
    raw = (payload.refresh_token if payload else None) or request.cookies.get(
        settings.refresh_cookie_name
    )
    if not raw:
        from ..errors import Unauthorized

        raise Unauthorized("Yenileme token'ı bulunamadı.")
    result = service.refresh(db, settings, raw)
    set_auth_cookies(
        response,
        settings,
        result.access_token,
        result.refresh_token,
        new_csrf_token(),
        settings.refresh_token_ttl_days * 86_400,
        settings.access_token_ttl_minutes * 60,
    )
    return result


@router.post("/logout", response_model=MessageOut)
def logout(
    request: Request,
    response: Response,
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageOut:
    raw = request.cookies.get(settings.refresh_cookie_name)
    result = service.logout(db, settings, raw)
    clear_auth_cookies(response, settings)
    return result


@router.post("/logout-all", response_model=MessageOut)
def logout_all(
    response: Response,
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user=Depends(require_user),
) -> MessageOut:
    result = service.logout_all(db, user.id)
    clear_auth_cookies(response, settings)
    return result


@router.get("/me", response_model=UserOut)
def me(db: D1Client = Depends(get_db), user=Depends(require_user)) -> UserOut:
    from ..repositories import users as user_repo

    row = user_repo.get_by_id(db, user.id)
    if not row:
        from ..errors import Unauthorized

        raise Unauthorized()
    return UserOut(
        id=str(row["id"]),
        email=str(row["email"]),
        name=row.get("name"),
        role=str(row.get("role") or "user"),
        is_active=bool(int(row.get("is_active") or 0)),
        email_verified=bool(int(row.get("email_verified") or 0)),
        created_at=row.get("created_at"),
        last_login_at=row.get("last_login_at"),
    )


@router.post("/password/forgot", response_model=MessageOut)
def password_forgot(
    email: str = Query(min_length=3),
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageOut:
    return service.request_password_reset(db, settings, email)


@router.post("/password/reset", response_model=MessageOut)
def password_reset(
    payload: PasswordResetIn,
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageOut:
    return service.reset_password(db, settings, payload.token, payload.new_password)
