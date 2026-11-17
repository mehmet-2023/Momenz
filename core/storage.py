from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .config import get_storage_config
from .store_base import StoreError

if TYPE_CHECKING:  # pragma: no cover
    from .d1_store import D1Store


def create_store(
    backend: str | None = None,
    config: dict[str, Any] | None = None,
):
    """Cloudflare D1 store oluşturur.

    ``backend``/``config`` verilmezse ``get_storage_config()`` sonucu
    kullanılır.
    """
    if backend is None or config is None:
        backend, config = get_storage_config()

    if backend == "d1" and config:
        from .d1_store import D1Store

        return D1Store(config)

    raise StoreError(
        "Veritabanı ayarı bulunamadı. Cloudflare D1 için secrets dosyasına "
        "[cloudflare_d1] tablosu (account_id, database_id, api_token) veya "
        "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_D1_DATABASE_ID / "
        "CLOUDFLARE_D1_API_TOKEN ekleyin."
    )
