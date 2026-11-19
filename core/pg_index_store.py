from __future__ import annotations

import base64
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import numpy as np

from .config import EMBEDDING_SIZE

# Embedding matrisleri, Streamlit her rerun'unda yeniden indirilmesin diye
# modül düzeyinde (süreç ömrü boyunca) önbelleğe alınır. D1'den klasör
# başına onlarca MB çekmek yerine yalnızca küçük bir meta sorgusu yapılır;
# sürüm değişmediyse matris bellekten döner.
_MATRIX_CACHE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_MATRIX_CACHE_BYTES = 0
_MATRIX_CACHE_MAX_BYTES = 128 * 1024 * 1024
_MATRIX_CACHE_TTL_SECONDS = 600.0
_MATRIX_CACHE_LOCK = threading.Lock()

# Klasör istatistikleri her rerun'da tüm klasörü taramasın diye kısa
# ömürlü bir önbellek. Anahtar: (backend kimliği, klasör, sürüm).
_STATS_CACHE: "OrderedDict[tuple[str, str, str], tuple[float, dict]]" = OrderedDict()
_STATS_CACHE_MAX_ENTRIES = 64
_STATS_CACHE_TTL_SECONDS = 300.0
_STATS_CACHE_LOCK = threading.Lock()


def clear_stats_cache(folder_key: str | None = None) -> None:
    with _STATS_CACHE_LOCK:
        if folder_key is None:
            _STATS_CACHE.clear()
            return
        for key in [item for item in _STATS_CACHE if item[1] == folder_key]:
            _STATS_CACHE.pop(key, None)


def _cached_folder_stats(
    pg: Any, folder_key: str, version: str
) -> dict:
    identity = getattr(pg, "cache_identity", None)
    backend_id = str(identity()) if callable(identity) else type(pg).__name__
    key = (backend_id, folder_key, version)
    now = time.monotonic()

    with _STATS_CACHE_LOCK:
        entry = _STATS_CACHE.get(key)
        if entry is not None and (now - entry[0]) <= _STATS_CACHE_TTL_SECONDS:
            _STATS_CACHE.move_to_end(key)
            return dict(entry[1])

    stats = pg.folder_stats(folder_key)

    with _STATS_CACHE_LOCK:
        _STATS_CACHE[key] = (now, dict(stats))
        while len(_STATS_CACHE) > _STATS_CACHE_MAX_ENTRIES:
            _STATS_CACHE.popitem(last=False)
    return stats


def clear_matrix_cache(folder_key: str | None = None) -> None:
    """Bellekteki embedding matrisi önbelleğini temizler."""
    global _MATRIX_CACHE_BYTES
    with _MATRIX_CACHE_LOCK:
        if folder_key is None:
            _MATRIX_CACHE.clear()
            _MATRIX_CACHE_BYTES = 0
            return
        entry = _MATRIX_CACHE.pop(folder_key, None)
        if entry is not None:
            _MATRIX_CACHE_BYTES = max(
                0, _MATRIX_CACHE_BYTES - int(entry.get("size") or 0)
            )


def _matrix_cache_size(matrix: np.ndarray, metas: list[dict]) -> int:
    return int(matrix.nbytes) + len(metas) * 256


def _matrix_cache_get(
    folder_key: str, version: tuple[str, str]
) -> tuple[np.ndarray, list[dict]] | None:
    global _MATRIX_CACHE_BYTES
    with _MATRIX_CACHE_LOCK:
        entry = _MATRIX_CACHE.get(folder_key)
        if entry is None:
            return None
        if entry.get("version") != version:
            _MATRIX_CACHE.pop(folder_key, None)
            _MATRIX_CACHE_BYTES = max(
                0, _MATRIX_CACHE_BYTES - int(entry.get("size") or 0)
            )
            return None
        if (time.monotonic() - float(entry.get("stored_at") or 0.0)) > (
            _MATRIX_CACHE_TTL_SECONDS
        ):
            _MATRIX_CACHE.pop(folder_key, None)
            _MATRIX_CACHE_BYTES = max(
                0, _MATRIX_CACHE_BYTES - int(entry.get("size") or 0)
            )
            return None
        _MATRIX_CACHE.move_to_end(folder_key)
        return entry["matrix"], entry["metas"]


def _matrix_cache_put(
    folder_key: str,
    version: tuple[str, str],
    matrix: np.ndarray,
    metas: list[dict],
) -> None:
    global _MATRIX_CACHE_BYTES
    size = _matrix_cache_size(matrix, metas)
    if size > _MATRIX_CACHE_MAX_BYTES:
        return

    with _MATRIX_CACHE_LOCK:
        previous = _MATRIX_CACHE.pop(folder_key, None)
        if previous is not None:
            _MATRIX_CACHE_BYTES = max(
                0, _MATRIX_CACHE_BYTES - int(previous.get("size") or 0)
            )
        while _MATRIX_CACHE and (
            _MATRIX_CACHE_BYTES + size > _MATRIX_CACHE_MAX_BYTES
        ):
            _, evicted = _MATRIX_CACHE.popitem(last=False)
            _MATRIX_CACHE_BYTES = max(
                0, _MATRIX_CACHE_BYTES - int(evicted.get("size") or 0)
            )
        _MATRIX_CACHE[folder_key] = {
            "version": version,
            "matrix": matrix,
            "metas": metas,
            "size": size,
            "stored_at": time.monotonic(),
        }
        _MATRIX_CACHE_BYTES += size


def _encode_faces(faces: list[dict]) -> list[dict]:
    payload: list[dict] = []
    for face in faces or []:
        embedding = face.get("embedding")
        if embedding is None:
            continue
        array = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if array.size != EMBEDDING_SIZE:
            continue
        bbox = face.get("bbox") or (0, 0, 0, 0)
        payload.append(
            {
                "x": float(bbox[0]),
                "y": float(bbox[1]),
                "w": float(bbox[2]),
                "h": float(bbox[3]),
                "score": float(face.get("det_score") or 0.0),
                "emb": base64.b64encode(
                    array.astype(np.float32).tobytes()
                ).decode("ascii"),
            }
        )
    return payload


class PgIndexStore:
    """Tek bir klasörün indeksini aktif veritabanında tutan store. Yerel SQL yoktur."""

    def __init__(self, store: Any, folder_key: str) -> None:
        self.pg = store
        self.folder_key = folder_key
        self._cache: tuple[np.ndarray, list[dict]] | None = None
        self._pending: list[dict] = []
        self._pending_limit = 100
        # Bu çalışmada değişen dosyalar; matrisi tam taramadan güncellemek için
        # worker'a aktarılır (artımlı index yolunda yalnızca birkaç dosya).
        self._changed_file_ids: set[str] = set()

    def flush(self) -> None:
        if not self._pending:
            return
        rows = self._pending
        self._pending = []
        self.pg.upsert(self.folder_key, rows)

    # ------------------------------------------------------------------- meta

    def set_meta(self, key: str, value: str) -> None:
        self.pg.set_folder_meta(self.folder_key, key, str(value))

    def meta_get(self, key: str, default: str | None = None) -> str | None:
        return self.pg.get_folder_meta(self.folder_key, key, default)

    # ------------------------------------------------------------------ writes

    def changed_file_ids(self) -> set[str]:
        return set(self._changed_file_ids)

    def save_result(
        self,
        file_id: str,
        name: str,
        path: str,
        width: int,
        height: int,
        faces: list[dict],
        status: str,
        error: str | None = None,
        *,
        commit: bool = True,
    ) -> None:
        self._cache = None
        clear_matrix_cache(self.folder_key)
        self._changed_file_ids.add(str(file_id))
        self._pending.append(
            {
                "file_id": file_id,
                "name": name,
                "path": path,
                "width": int(width),
                "height": int(height),
                "status": status,
                "error": error,
                "faces": _encode_faces(faces),
            }
        )
        if len(self._pending) >= self._pending_limit:
            self.flush()

    def save_error(
        self,
        file_id: str,
        name: str,
        path: str,
        error: str,
        *,
        commit: bool = True,
    ) -> None:
        self.save_result(
            file_id=file_id,
            name=name,
            path=path,
            width=0,
            height=0,
            faces=[],
            status="error",
            error=error,
            commit=commit,
        )

    def claim_images(
        self,
        file_ids: list[str],
        *,
        force: bool = False,
        stale_minutes: int = 30,
    ) -> set[str]:
        self.flush()
        return self.pg.claim_images(
            self.folder_key,
            file_ids,
            force=force,
            stale_minutes=stale_minutes,
        )

    def import_rows(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        self._cache = None
        clear_matrix_cache(self.folder_key)
        self._pending.extend(rows)
        if len(self._pending) >= self._pending_limit:
            self.flush()
        return len(rows)

    def set_indexed_at(self) -> None:
        self.set_meta(
            "last_indexed",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    # ------------------------------------------------------------------- reads

    def has_image(self, file_id: str) -> bool:
        self.flush()
        return self.pg.has_image(self.folder_key, file_id)

    def sample_image(self) -> tuple[str, str] | None:
        self.flush()
        return self.pg.sample_image(self.folder_key)

    def done_ids(self) -> set[str]:
        self.flush()
        return self.pg.done_ids(self.folder_key)

    def stats(self) -> dict:
        self.flush()
        return self.pg.folder_stats(self.folder_key)

    def stats_cached(self, version: str | None = None) -> dict:
        """``stats`` sonucunu klasör sürümüne göre önbellekten döndürür."""
        self.flush()
        if version is None:
            version = self.matrix_version_string()
        return _cached_folder_stats(self.pg, self.folder_key, version)

    def matrix_version_string(self) -> str:
        try:
            meta = self.pg.get_folder_meta_dict(self.folder_key)
        except Exception:
            return ""
        return f"{meta.get('last_indexed') or ''}|{meta.get('folder_count') or ''}"

    def load_matrix(self) -> tuple[np.ndarray, list[dict]]:
        if self._cache is not None:
            return self._cache

        self.flush()
        version = self._matrix_version()
        cached = _matrix_cache_get(self.folder_key, version)
        if cached is not None:
            self._cache = cached
            return cached

        rows = self.pg.fetch(self.folder_key)
        embeddings: list[np.ndarray] = []
        metas: list[dict] = []
        for row in rows:
            if str(row.get("status") or "") != "done":
                continue
            for face in row.get("faces") or []:
                try:
                    raw = base64.b64decode(str(face.get("emb") or ""))
                    embedding = np.frombuffer(raw, dtype=np.float32)
                except Exception:
                    continue
                if embedding.size != EMBEDDING_SIZE:
                    continue
                embeddings.append(embedding.copy())
                metas.append(
                    {
                        "file_id": str(row.get("file_id") or ""),
                        "name": str(row.get("name") or ""),
                        "path": str(row.get("path") or ""),
                        "width": int(row.get("width") or 0),
                        "height": int(row.get("height") or 0),
                        "bbox": (
                            float(face.get("x") or 0.0),
                            float(face.get("y") or 0.0),
                            float(face.get("w") or 0.0),
                            float(face.get("h") or 0.0),
                        ),
                        "det_score": float(face.get("score") or 0.0),
                    }
                )

        if embeddings:
            matrix = np.stack(embeddings).astype(np.float32)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            np.divide(matrix, norms, out=matrix, where=norms > 1e-8)
        else:
            matrix = np.zeros((0, EMBEDDING_SIZE), dtype=np.float32)

        self._cache = (matrix, metas)
        _matrix_cache_put(self.folder_key, version, matrix, metas)
        return matrix, metas

    def _matrix_version(self) -> tuple[str, str]:
        """Matrisin tazeliğini belirleyen hafif sürüm anahtarı."""
        try:
            meta = self.pg.get_folder_meta_dict(self.folder_key)
        except Exception:
            return ("", "")
        return (
            str(meta.get("last_indexed") or ""),
            str(meta.get("folder_count") or ""),
        )

    def clear(self) -> None:
        self._cache = None
        self._pending = []
        self._changed_file_ids.clear()
        clear_matrix_cache(self.folder_key)
        clear_stats_cache(self.folder_key)
        self.pg.clear_folder(self.folder_key)

    def close(self) -> None:
        return None
