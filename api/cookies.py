from __future__ import annotations

from fastapi import Response

from .config import Settings


def _common(settings: Settings) -> dict:
    return {
        "path": "/",
        "secure": settings.cookie_secure,
        "httponly": True,
        "samesite": settings.cookie_samesite,
        **({"domain": settings.cookie_domain} if settings.cookie_domain else {}),
    }


def set_auth_cookies(
    response: Response,
    settings: Settings,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    refresh_max_age: int,
) -> None:
    response.set_cookie(
        settings.cookie_name,
        access_token,
        max_age=15 * 60,
        **_common(settings),
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        refresh_token,
        max_age=refresh_max_age,
        **_common(settings),
    )
    # CSRF token JS'in okuyabilmesi için httpOnly DEĞİL.
    # Saldırgan bunu cross-origin okuyamaz (CORS + same-origin policy).
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=refresh_max_age,
        path="/",
        secure=settings.cookie_secure,
        httponly=False,
        samesite=settings.cookie_samesite,
        **({"domain": settings.cookie_domain} if settings.cookie_domain else {}),
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    for name in (
        settings.cookie_name,
        settings.refresh_cookie_name,
        settings.csrf_cookie_name,
    ):
        response.delete_cookie(
            name,
            path="/",
            secure=settings.cookie_secure,
            httponly=True,
            samesite=settings.cookie_samesite,
            **({"domain": settings.cookie_domain} if settings.cookie_domain else {}),
        )
