from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Tüm yapılandırma ortam değişkenlerinden gelir (MOMENZ_ prefix).

    Streamlit secrets kullanılmaz. Cloud Run / Modal / Oracle VM fark etmeksizin
    aynı env değişkenleri okunur.
    """

    model_config = SettingsConfigDict(
        env_prefix="MOMENZ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------------------------------------------------------- app
    app_name: str = "Momenz API"
    environment: str = "dev"
    debug: bool = False
    api_base_url: str = "https://momenz.onrender.com"
    web_base_url: str = "https://momenz.vercel.app"
    # NoDecode: pydantic-settings bu alanları JSON sanıp çözmesin;
    # virgülle ayrılmış env değerini _split_lists kendisi parselesin.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["https://momenz.vercel.app"]
    )

    # ---------------------------------------------------------------- Turso
    # Cloudflare D1, row-read kotası dolduğu için source of truth Turso'ya
    # taşındı. Eski D1 alanları yalnızca geri dönüş/uyumluluk için duruyor.
    turso_database_url: str = ""
    turso_auth_token: str = ""
    turso_timeout_connect: float = 10.0
    # Klasör başına ~20 MB BLOB yazımı/okuması için geniş timeout.
    turso_timeout_read: float = 600.0
    turso_max_retries: int = 4

    # Eski D1 ayarları (artık kullanılmaz; d1_config yine Turso döner).
    d1_account_id: str = ""
    d1_database_id: str = ""
    d1_api_token: str = ""
    d1_timeout_connect: float = 10.0
    d1_timeout_read: float = 90.0
    d1_max_retries: int = 4

    # ---------------------------------------------------------------- auth
    jwt_secret: str = "dev-only-change-this-secret"
    jwt_algorithm: str = "HS256"
    # Oturum süresiz: kullanıcı çıkış yapmadıkça / şifresi değişmedikçe
    # tekrar giriş yapmaz. (10 yıl, pratikte tarayıcı oturumu kadar kalıcı.)
    access_token_ttl_minutes: int = 60 * 24 * 365 * 10
    refresh_token_ttl_days: int = 365 * 10
    verification_ttl_hours: int = 24
    cookie_name: str = "momenz_access"
    refresh_cookie_name: str = "momenz_refresh"
    csrf_cookie_name: str = "momenz_csrf"
    csrf_header: str = "X-CSRF-Token"
    cookie_secure: bool = False
    cookie_domain: str | None = None
    cookie_samesite: str = "lax"
    login_rate_limit: int = 10  # dakikadaki deneme sayısı (IP + e-posta)
    trusted_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "momenz.onrender.com",
            "localhost",
            "127.0.0.1",
        ]
    )
    hsts_max_age: int = 31_536_000

    # ---------------------------------------------------------------- Google
    google_drive_api_key: str = ""
    google_service_account_json: str = ""
    google_credentials_file: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""

    # ---------------------------------------------------------------- search
    # Render free 512 MB: klasör başına ~20 MB matris + metadata; tek klasör
    # sıcak tutulur, diğer klasöre geçince eskisi derhal serbest bırakılır.
    search_cache_max_folders: int = 1
    search_default_threshold: float = 0.50
    search_max_results: int = 200
    preview_thumb_size: int = 384

    # ---------------------------------------------------------------- jobs
    job_stale_minutes: int = 30
    job_poll_seconds: float = 2.0
    job_max_progress_writes: int = 200

    # ---------------------------------------------------------------- mail
    # Gmail SMTP (Resend kaldırıldı). Gmail App Password gerekir; normal hesap
    # şifresi SMTP ile çalışmaz. 2FA açık olmalı.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_timeout: int = 20
    mail_from: str = "Momenz <no-reply@momenz.com>"
    mail_reset_url: str = (
        "https://momenz.vercel.app/sifre-sifirla?token={token}"
    )

    # ---------------------------------------------------------------- cache
    thumb_cache_dir: str = "/tmp/momenz_thumbs"
    thumb_cache_ttl_seconds: int = 86_400

    @field_validator("cors_origins", "trusted_hosts", mode="before")
    @classmethod
    def _split_lists(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _enforce_production_security(self) -> "Settings":
        # Prod'da zayıf/placeholder secret ile açılış yapılmasın.
        if self.is_production:
            weak = {
                "dev-only-change-this-secret",
                "secret",
                "changeme",
                "change-me",
                "",
            }
            if self.jwt_secret.strip().lower() in weak or len(self.jwt_secret) < 32:
                raise ValueError(
                    "MOMENZ_JWT_SECRET üretimde en az 32 karakterli, rastgele "
                    "bir değer olmak zorundadır (bkz. scripts/gen_env.py)."
                )
            if not self.cookie_secure:
                raise ValueError(
                    "Üretimde MOMENZ_COOKIE_SECURE=true olmak zorundadır."
                )
            if "*" in self.trusted_hosts:
                raise ValueError(
                    "Üretimde MOMENZ_TRUSTED_HOSTS açıkça belirtilmelidir."
                )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production", "live"}

    @property
    def db_config(self) -> dict[str, Any]:
        return {
            "database_url": self.turso_database_url,
            "auth_token": self.turso_auth_token,
            "timeout": (self.turso_timeout_connect, self.turso_timeout_read),
            "max_retries": self.turso_max_retries,
        }

    def db_ready(self) -> bool:
        return bool(self.turso_database_url and self.turso_auth_token)

    @property
    def d1_config(self) -> dict[str, Any]:
        """Eski çağrılar için uyumluluk diğer adı; Turso yapılandırması."""
        return self.db_config

    def d1_ready(self) -> bool:
        return self.db_ready()

    def service_account_info(self) -> dict[str, Any] | None:
        """Core'un eski secrets zincirini bozmadan env'den servis hesabı üretir."""
        if self.google_service_account_json:
            try:
                info = json.loads(self.google_service_account_json)
                if info.get("type") == "service_account":
                    return info
            except (TypeError, ValueError):
                pass
        if self.google_credentials_file:
            try:
                with open(self.google_credentials_file, encoding="utf-8") as handle:
                    info = json.load(handle)
                if info.get("type") == "service_account":
                    return info
            except (OSError, ValueError):
                pass
        # Yerel geliştirmede core.config zaten credentials.json'u okuyor.
        from core.config import get_service_account_info

        return get_service_account_info()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
