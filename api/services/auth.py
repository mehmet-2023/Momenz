from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..config import Settings
from ..db import D1Client
from ..errors import Conflict, Forbidden, InvalidCredentials, NotFound, Unauthorized, UpstreamError
from ..repositories import users as repo
from ..schemas import (
    LoginIn,
    MessageOut,
    RegisterIn,
    TokenPair,
    UserOut,
)
from ..security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    needs_rehash,
    new_id,
    new_csrf_token,
    token_fingerprint,
    verify_password,
)
from .mail import send_mail

log = logging.getLogger("momenz.auth")


def _user_out(row: dict) -> UserOut:
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


def register(db: D1Client, settings: Settings, payload: RegisterIn) -> MessageOut:
    email = str(payload.email).strip().lower()
    if repo.get_by_email(db, email):
        # Kullanıcı varlığını doğrudan belli etmeyelim.
        return MessageOut(
            message="Bu e-posta ile bir kayıt oluşturulduysa doğrulama bağlantısı gönderildi."
        )

    user_id = new_id()
    repo.create_user(
        db,
        user_id=user_id,
        email=email,
        name=payload.name,
        password_hash=hash_password(payload.password),
    )

    raw, fingerprint, _ = create_refresh_token(settings, user_id)
    import jwt

    claims = decode_token(settings, raw, "refresh")
    claims["type"] = "verify_email"
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    claims["exp"] = now + timedelta(hours=settings.verification_ttl_hours)
    raw = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    repo.create_verification_token(
        db, new_id(), user_id, "verify_email", token_fingerprint(raw),
        settings.verification_ttl_hours,
    )

    link = settings.mail_verify_url.format(token=raw)
    sent = send_mail(
        settings,
        email,
        "Momenz — e-postanı doğrula",
        f"E-postanı doğrulamak için bağlantıyı aç:\n\n{link}\n\n"
        "Bu bağlantı sınırlı süre geçerlidir.",
    )
    if not sent:
        log.warning("Doğrulama maili gönderilemedi (user=%s)", user_id)

    return MessageOut(
        message="Kayıt oluşturuldu. E-postanı doğrulayarak giriş yapabilirsin."
    )


def verify_email(db: D1Client, settings: Settings, token: str) -> MessageOut:
    claims = decode_token(settings, token, "verify_email")
    row = repo.consume_verification_token(
        db, token_fingerprint(token), "verify_email"
    )
    if not row or str(row.get("user_id")) != str(claims.get("sub")):
        raise Unauthorized("Doğrulama bağlantısı geçersiz veya kullanılmış.")
    repo.set_email_verified(db, str(row["user_id"]))
    return MessageOut(message="E-posta doğrulandı. Şimdi giriş yapabilirsin.")


def login(db: D1Client, settings: Settings, payload: LoginIn) -> TokenPair:
    row = repo.get_by_email(db, str(payload.email))
    if not row or not verify_password(str(row.get("password_hash") or ""), payload.password):
        # Aynı mesaj: kullanıcı sayımı (user enumeration) engellenir.
        raise InvalidCredentials()

    if needs_rehash(str(row["password_hash"])):
        repo.set_password(db, str(row["id"]), hash_password(payload.password))

    if not int(row.get("is_active") or 0):
        raise Forbidden("Hesap devre dışı bırakılmış.")
    if not int(row.get("email_verified") or 0):
        raise Forbidden("Önce e-posta adresini doğrula.")

    user = _user_out(row)
    access, access_ttl = create_access_token(
        settings, user.id, user.email, user.role
    )
    refresh, fingerprint, expires_at = create_refresh_token(settings, user.id)
    from ..security import new_id as _new_id

    repo.store_refresh_token(db, _new_id(), user.id, fingerprint, expires_at)
    repo.update_last_login(db, user.id)
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=access_ttl,
        user=user,
    )


def refresh(db: D1Client, settings: Settings, raw_token: str) -> TokenPair:
    claims = decode_token(settings, raw_token, "refresh")
    fingerprint = token_fingerprint(raw_token)
    stored = repo.get_refresh_token(db, fingerprint)
    if not stored:
        raise Unauthorized("Oturum bulunamadı.")

    if stored.get("revoked_at"):
        # Rotation token'ın tekrar kullanılması: tüm oturumları düşür.
        repo.revoke_all_for_user(db, str(stored["user_id"]))
        raise Unauthorized("Token tekrar kullanıldı; tüm oturumların kapatıldı.")

    if str(stored.get("user_id")) != str(claims.get("sub")):
        raise Unauthorized("Oturum geçersiz.")

    row = repo.get_by_id(db, str(stored["user_id"]))
    if not row or not int(row.get("is_active") or 0):
        raise Unauthorized("Hesap devre dışı.")

    # Rotation: eski token'ı iptal et, yeni çift üret.
    repo.revoke_refresh_token(db, fingerprint)
    user = _user_out(row)
    access, access_ttl = create_access_token(settings, user.id, user.email, user.role)
    new_refresh, new_fingerprint, expires_at = create_refresh_token(settings, user.id)
    repo.store_refresh_token(db, new_id(), user.id, new_fingerprint, expires_at)
    return TokenPair(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=access_ttl,
        user=user,
    )


def logout(db: D1Client, settings: Settings, raw_refresh: str | None) -> MessageOut:
    if raw_refresh:
        try:
            claims = decode_token(settings, raw_refresh, "refresh")
            repo.revoke_refresh_token(db, token_fingerprint(raw_refresh))
            log.info("Logout: user=%s", claims.get("sub"))
        except Unauthorized:
            pass
    return MessageOut(message="Oturum kapatıldı.")


def logout_all(db: D1Client, user_id: str) -> MessageOut:
    repo.revoke_all_for_user(db, user_id)
    return MessageOut(message="Tüm oturumlar kapatıldı.")


def request_password_reset(db: D1Client, settings: Settings, email: str) -> MessageOut:
    generic = MessageOut(
        message="Bu e-posta kayıtlıysa şifre sıfırlama bağlantısı gönderildi."
    )
    row = repo.get_by_email(db, email)
    if not row:
        return generic
    raw, fingerprint, _ = create_refresh_token(settings, str(row["id"]))
    import jwt
    from datetime import timedelta

    claims = decode_token(settings, raw, "refresh")
    claims["type"] = "password_reset"
    claims["exp"] = datetime.now(timezone.utc) + timedelta(
        hours=settings.verification_ttl_hours
    )
    raw = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    repo.create_verification_token(
        db, new_id(), str(row["id"]), "password_reset", token_fingerprint(raw),
        settings.verification_ttl_hours,
    )
    link = settings.mail_reset_url.format(token=raw)
    send_mail(
        settings,
        str(row["email"]),
        "Momenz — şifre sıfırlama",
        f"Şifreni sıfırlamak için:\n\n{link}\n\n"
        "Bu bağlantıyı kimseyle paylaşma.",
    )
    return generic


def reset_password(
    db: D1Client, settings: Settings, token: str, new_password: str
) -> MessageOut:
    claims = decode_token(settings, token, "password_reset")
    row = repo.consume_verification_token(db, token_fingerprint(token), "password_reset")
    if not row or str(row.get("user_id")) != str(claims.get("sub")):
        raise Unauthorized("Sıfırlama bağlantısı geçersiz veya kullanılmış.")
    user_id = str(row["user_id"])
    repo.set_password(db, user_id, hash_password(new_password))
    repo.revoke_all_for_user(db, user_id)
    return MessageOut(message="Şifren güncellendi. Tüm oturumlar kapatıldı, tekrar giriş yap.")


def csrf_token() -> str:
    """GET /auth/csrf için公开 token (httpOnly olmayan cookie'ye yazılır)."""
    return new_csrf_token()
