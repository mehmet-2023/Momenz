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


@lru_cache(maxsize=1)
def _cached_thumb_client() -> DriveClient:
    """Thumbnail için hızlı başarısız olan istemci.

    Önizleme isteği tam dosya indirmesi değildir; uzun timeout + 4 retry,
    soğuk cache'te eşzamanlı thumbnail patlamasını dakikalara çıkarıp
    502/503 üretiyordu. Kısa timeout ve sıfır retry ile sınırlı tutulur.
    """
    settings = get_settings()
    return DriveClient(
        api_key=settings.google_drive_api_key or None,
        service_account_info=settings.service_account_info(),
        timeout=(4.0, 12.0),
        max_retries=0,
    )


def get_drive_client(settings: Settings | None = None) -> DriveClient:
    """Drive istemcisini tek sefer oluşturup paylaşır (argüman uyumluluğu korunur)."""
    return _cached_drive_client()


def get_thumbnail_drive_client(settings: Settings | None = None) -> DriveClient:
    """Thumbnail uçları için kısa timeout'lu paylaşılan Drive istemcisi."""
    return _cached_thumb_client()
