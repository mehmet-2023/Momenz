from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .config import get_storage_config
from .store_base import StoreError

if TYPE_CHECKING:  # pragma: no cover
    from .d1_store import D1Store
    from .turso_store import TursoStore


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

    if backend == "turso" and config:
        from .turso_store import TursoStore

        return TursoStore(config)

    if backend == "d1" and config:
        from .d1_store import D1Store

        return D1Store(config)

    raise StoreError(
        "Veritabanı ayarı bulunamadı. MOMENZ_TURSO_DATABASE_URL ve "
        "MOMENZ_TURSO_AUTH_TOKEN değişkenlerini ayarlayın."
    )
