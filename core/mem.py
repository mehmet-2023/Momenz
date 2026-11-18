from __future__ import annotations

import ctypes
import gc

_libc = None
try:  # glibc varsa serbest baytları OS'a geri ver.
    _libc = ctypes.CDLL("libc.so.6")
except Exception:  # pragma: no cover - musl / Windows
    _libc = None


def release_memory() -> None:
    """Büyük geçici verilerden sonra malloc arenasını küçült."""
    gc.collect()
    if _libc is not None:
        try:
            trim = getattr(_libc, "malloc_trim", None)
            if trim is not None:
                trim(0)
        except Exception:
            pass
