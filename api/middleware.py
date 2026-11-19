from __future__ import annotations

import hmac
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from .config import Settings

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class RootExemptTrustedHostMiddleware(TrustedHostMiddleware):
    """Host kısıtını kök yol dışındaki tüm yollarda uygula.

    Render/PaaS port kontrolleri Host header'ı public domain yerine iç
    hostname ya da IP ile gönderebilir. Sahte Host ile API yollarına erişim
    kapalı kalır; yalnızca ``/`` muaftır.
    """

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/":
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:  
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(self), microphone=(), geolocation=(), payment=()",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Content-Security-Policy": (
                "default-src 'self'; "
                "img-src 'self' data: blob: https://lh3.googleusercontent.com "
                "https://drive.usercontent.google.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "script-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
            ),
        }
        if self.settings.is_production and request.url.scheme == "https":
            headers["Strict-Transport-Security"] = (
                f"max-age={self.settings.hsts_max_age}; includeSubDomains"
            )
        for key, value in headers.items():
            response.headers.setdefault(key, value)
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Cookie ile yapılan yazma isteklerinde double-submit CSRF zorunluluğu.

    Bearer token kullanan API istemcileri CSRF'e tabii değildir; CSRF yalnızca
    tarayıcının otomatik gönderdiği httpOnly cookie'yi hedefleyen saldırılara
    karşı koruma sağlar.
    """

    def __init__(self, app, settings: Settings) -> None:  
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in _UNSAFE:
            has_bearer = request.headers.get("Authorization", "").lower().startswith("bearer ")
            has_access_cookie = bool(request.cookies.get(self.settings.cookie_name))
            if has_access_cookie and not has_bearer:
                cookie_token = request.cookies.get(self.settings.csrf_cookie_name, "")
                header_token = request.headers.get(self.settings.csrf_header, "")
                if (
                    not cookie_token
                    or not header_token
                    or not hmac.compare_digest(cookie_token, header_token)
                ):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": {
                                "code": "csrf_failed",
                                "message": "CSRF doğrulaması başarısız.",
                                "request_id": getattr(request.state, "request_id", None),
                            }
                        },
                    )
        return await call_next(request)
