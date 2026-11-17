from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "İstek işlenemedi."

    def __init__(self, message: str | None = None, detail: Any = None) -> None:
        self.message = message or self.message
        self.detail = detail
        super().__init__(self.message)


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Giriş yapman gerekiyor."


class InvalidCredentials(AppError):
    status_code = 401
    code = "invalid_credentials"
    message = "E-posta veya şifre hatalı."


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    message = "Bu kaynağa erişim iznin yok."


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    message = "Kayıt bulunamadı."


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    message = "Bu kayıt zaten var."


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Çok fazla deneme yaptın. Biraz bekleyip tekrar dene."


class UpstreamError(AppError):
    status_code = 502
    code = "upstream_error"
    message = "Bağlı olduğumuz servis şu an yanıt vermiyor."


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Beklenmedik bir sunucu hatası oluştu.",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )
