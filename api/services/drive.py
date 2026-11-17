from __future__ import annotations

from functools import lru_cache

from core.drive import DriveClient

from ..config import Settings, get_settings


@lru_cache(maxsize=1)
def get_drive_client(settings: Settings | None = None) -> DriveClient:
    settings = settings or get_settings()
    return DriveClient(
        api_key=settings.google_drive_api_key or None,
        service_account_info=settings.service_account_info(),
    )
