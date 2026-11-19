from __future__ import annotations

import threading
import time
from pathlib import Path

from core.image_utils import encode_jpeg_bytes

from ..config import Settings

# Soğuk cache'te 60+ eşzamanlı thumbnail isteği Drive'ı ve Render/Vercel
# proxy'sini boğuyor, tek tek istekler 502/503'e düşüyordu. Süreç genelinde
# eşzamanlı Drive önizleme sayısı sınırlanır.
_MAX_CONCURRENT_FETCHES = 8
# Aynı dosya için bekleyen isteklerin üst sınırı; kuyruk proxy timeout'una
# girmesin diye kısa tutulur.
_LOCK_WAIT_SECONDS = 20.0
_SLOT_WAIT_SECONDS = 12.0
# Başarısız dosyayı kısa süre hatırla: aynı bozuk ID'ye istek fırtınası olmasın.
_NEGATIVE_TTL_SECONDS = 45.0
# Drive thumbnail için yalnızca ilk kaynaklar denenir (drive + lh3 + lh4).
_MAX_CANDIDATES = 3

_slots = threading.BoundedSemaphore(_MAX_CONCURRENT_FETCHES)
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()
_negative: dict[str, float] = {}
_negative_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def _is_negative(key: str) -> bool:
    with _negative_guard:
        until = _negative.get(key)
        if until is None:
            return False
        if until <= time.monotonic():
            _negative.pop(key, None)
            return False
        return True


def _mark_negative(key: str) -> None:
    now = time.monotonic()
    with _negative_guard:
        if len(_negative) > 4096:
            for stale in [k for k, until in _negative.items() if until <= now]:
                _negative.pop(stale, None)
        _negative[key] = now + _NEGATIVE_TTL_SECONDS


def _read_cached(path: Path, ttl_seconds: int) -> bytes | None:
    try:
        if path.exists() and (time.time() - path.stat().st_mtime) < ttl_seconds:
            return path.read_bytes()
    except OSError:
        return None
    return None


def _write_cached(path: Path, data: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    except OSError:
        # Cache yazılamasa bile yanıt dönebilir.
        pass


def render_thumbnail(
    settings: Settings,
    file_id: str,
    size: int,
    path: Path,
    *,
    quality: int = 78,
) -> bytes | None:
    """Thumbnail baytlarını disk cache'inden ya da Drive'dan üretir.

    Aynı dosya/boyut için eşzamanlı istekler tek Drive çağrısını paylaşır;
    tüm süreçte Drive'a giden eşzamanlı istek sayısı sınırlıdır. Böylece
    arama sonuçları veya kapaklar aynı anda yüklense bile arka uç toplu
    istek fırtınasına girmez.
    """
    ttl = settings.thumb_cache_ttl_seconds
    cached = _read_cached(path, ttl)
    if cached is not None:
        return cached

    key = f"{file_id}:{size}"
    if _is_negative(key):
        return None

    lock = _lock_for(key)
    if not lock.acquire(timeout=_LOCK_WAIT_SECONDS):
        return None
    try:
        # Bu dosyayı bekleyen başka bir istek diske yazmış olabilir.
        cached = _read_cached(path, ttl)
        if cached is not None:
            return cached
        if _is_negative(key):
            return None

        if not _slots.acquire(timeout=_SLOT_WAIT_SECONDS):
            return None
        try:
            from .drive import get_thumbnail_drive_client

            try:
                image = get_thumbnail_drive_client(settings).fetch_image(
                    file_id, size, max_candidates=_MAX_CANDIDATES
                )
            except Exception:
                # Tek bir Drive/credential hatası tüm uçları 500'e düşürmesin.
                image = None
        finally:
            _slots.release()

        if image is None:
            _mark_negative(key)
            return None

        try:
            data = encode_jpeg_bytes(image, quality=quality)
        except Exception:
            data = b""
        if not data:
            _mark_negative(key)
            return None

        _write_cached(path, data)
        return data
    finally:
        lock.release()
