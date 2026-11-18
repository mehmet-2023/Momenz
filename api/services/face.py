from __future__ import annotations

import threading

import numpy as np

from core.config import DEFAULT_DET_THRESHOLD, DEFAULT_MIN_FACE
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


def probe_embedding(image: np.ndarray) -> np.ndarray:
    """Görseldeki ilk yüzün 512 boyutlu vektörünü döner.

    Aynı motor hem /search hem de /search/embed tarafından kullanılır; böylece
    bir yüz iki kez analiz edilmez. Yüz yoksa boş vektör döner.
    """
    engine = get_face_engine()
    faces, _ = engine.analyze(
        image,
        det_threshold=DEFAULT_DET_THRESHOLD,
        min_face=DEFAULT_MIN_FACE,
        max_faces=5,
        input_max_side=768,
    )
    if not faces:
        return np.empty(0, dtype=np.float32)
    return np.asarray(faces[0]["embedding"], dtype=np.float32).reshape(-1)
