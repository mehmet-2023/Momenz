from __future__ import annotations

import threading

from core.face_engine import FaceEngine, ensure_models

_engine: FaceEngine | None = None
_lock = threading.Lock()


def get_face_engine() -> FaceEngine:
    """Yüz motorunu yalnızca ilk aramada yükler (startup RAM'ini düşürür)."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                yunet_path, sface_path = ensure_models()
                _engine = FaceEngine(yunet_path, sface_path, num_threads=1)
    return _engine


def face_engine_ready() -> bool:
    return _engine is not None
