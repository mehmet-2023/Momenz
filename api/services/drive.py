from __future__ import annotations

from functools import lru_cache

from core.drive import DriveClient

from ..config import Settings, get_settings


@lru_cache(maxsize=1)
def _cached_drive_client() -> DriveClient:
    # Settings pydantic modeli hash edilemediği için cache anahtarı olarak
    # kullanılamaz; tekil ayarları cache'li fonksiyonun içinde okuyoruz.
    settings = get_settings()
    return DriveClient(
        api_key=settings.google_drive_api_key or None,
        service_account_info=settings.service_account_info(),
    )


def get_drive_client(settings: Settings | None = None) -> DriveClient:
    """Drive istemcisini tek sefer oluşturup paylaşır (argüman uyumluluğu korunur)."""
    return _cached_drive_client()
