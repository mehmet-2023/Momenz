from __future__ import annotations

import base64
import json
from typing import Any

import numpy as np

from core.config import EMBEDDING_SIZE
from core.mem import release_memory

from ..db import D1Client

# Bu yol artık yalnızca iş bitiminde/backfill'de kullanılıyor (arama tek BLOB
# satırı okur). Turso'da 4000 satırlık sayfa, HTTP tur sayısını azaltır.
_PAGE_SIZE = 4000

_MATRIX_TABLE_READY: set[int] = set()

_MATRIX_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS folder_matrices (
    folder_key TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 0,
    is_public INTEGER NOT NULL DEFAULT 0,
    matrix BLOB NOT NULL,
    metas BLOB NOT NULL,
    rows INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def ensure_folder_matrices(db: D1Client) -> None:
    """Matris tablosunu süreç başına bir kez, idempotent olarak hazırlar."""
    identity = id(db)
    if identity in _MATRIX_TABLE_READY:
        return
    db.execute(_MATRIX_TABLE_SQL)
    _MATRIX_TABLE_READY.add(identity)


def folder_is_public(db: D1Client, folder_key: str) -> bool:
    row = db.query_one(
        "SELECT 1 FROM events WHERE folder_key = ? AND is_public = 1 LIMIT 1",
        (folder_key,),
    )
    return row is not None


def set_matrix_public(db: D1Client, folder_key: str, is_public: bool) -> None:
    """Etkinlik yayın durumu değiştiğinde matris satırını günceller."""
    ensure_folder_matrices(db)
    db.execute(
        "UPDATE folder_matrices SET is_public = ? WHERE folder_key = ?",
        (1 if is_public else 0, folder_key),
    )


def save_matrix(
    db: D1Client,
    folder_key: str,
    version: int,
    matrix: np.ndarray,
    metas: list[dict],
    *,
    is_public: bool | None = None,
) -> None:
    """Klasörün aranabilir matrisini tek satır olarak yazar."""
    ensure_folder_matrices(db)
    if is_public is None:
        is_public = folder_is_public(db, folder_key)
    array = np.ascontiguousarray(matrix, dtype=np.float32)
    if array.ndim != 2 or array.shape[1] != EMBEDDING_SIZE:
        raise ValueError("Matris boyutu EMBEDDING_SIZE ile uyuşmuyor.")
    if array.shape[0] != len(metas):
        raise ValueError("Matris satır sayısı metadata sayısı ile uyuşmuyor.")

    matrix_blob = array.tobytes()
    metas_blob = json.dumps(
        metas, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    db.execute(
        """
        INSERT INTO folder_matrices
            (folder_key, version, is_public, matrix, metas, rows, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT (folder_key) DO UPDATE SET
            version = excluded.version,
            is_public = excluded.is_public,
            matrix = excluded.matrix,
            metas = excluded.metas,
            rows = excluded.rows,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            folder_key,
            int(version),
            1 if is_public else 0,
            matrix_blob,
            metas_blob,
            int(array.shape[0]),
        ),
    )


def _decode_matrix_row(row: dict) -> tuple[np.ndarray, list[dict]] | None:
    try:
        count = int(row.get("rows") or 0)
        raw_matrix = row.get("matrix")
        if isinstance(raw_matrix, memoryview):
            raw_matrix = raw_matrix.tobytes()
        if not isinstance(raw_matrix, (bytes, bytearray)):
            return None
        array = np.frombuffer(bytes(raw_matrix), dtype=np.float32)
        if array.size != count * EMBEDDING_SIZE:
            return None
        matrix = array.reshape(count, EMBEDDING_SIZE).copy()

        raw_metas = row.get("metas")
        if isinstance(raw_metas, memoryview):
            raw_metas = raw_metas.tobytes()
        if isinstance(raw_metas, (bytes, bytearray)):
            raw_metas = bytes(raw_metas).decode("utf-8")
        metas = json.loads(str(raw_metas or "[]"))
        if not isinstance(metas, list) or len(metas) != count:
            return None
        return matrix, metas
    except (TypeError, ValueError, UnicodeDecodeError):
        return None


def load_matrix(
    db: D1Client, folder_key: str, version: int | None
) -> tuple[np.ndarray, list[dict]] | None:
    """Sürüm eşleşirse matrisi tek satırdan okur, aksi halde ``None``.

    ``version=None`` güncel sürümü dikkate almadan mevcut BLOB'u okur; worker
    incremental güncellemede bunu kullanır.
    """
    row = db.query_one(
        """
        SELECT version, matrix, metas, rows
        FROM folder_matrices WHERE folder_key = ? LIMIT 1
        """,
        (folder_key,),
    )
    if not row:
        return None
    if version is not None and int(row.get("version") or 0) != int(version):
        return None
    return _decode_matrix_row(row)


def public_version_matrix(
    db: D1Client, folder_key: str
) -> tuple[bool, int, tuple[np.ndarray, list[dict]] | None]:
    """Arama için gereken her şeyi TEK satır okumayla döndürür.

    Yayın durumu, index sürümü ve (sürüm güncelse) matris BLOB'u aynı sorguda
    gelir. Böylece arama başına Turso satır okuması 1'dir.
    """
    row = db.query_one(
        """
        SELECT is_public, version, matrix, metas, rows
        FROM folder_matrices WHERE folder_key = ? LIMIT 1
        """,
        (folder_key,),
    ) or {}
    version = int(row.get("version") or 0)
    matrix_data = None
    if row.get("matrix") is not None:
        matrix_data = _decode_matrix_row(row)
    return bool(row.get("is_public")), version, matrix_data


def _rows_to_embeddings(
    rows: list[dict],
) -> tuple[list[np.ndarray], list[dict]]:
    embeddings: list[np.ndarray] = []
    metas: list[dict] = []
    for row in rows:
        if str(row.get("status") or "") != "done":
            continue
        faces = row.get("faces")
        if isinstance(faces, str):
            try:
                faces = json.loads(faces)
            except ValueError:
                faces = []
        for face in faces or []:
            try:
                raw = base64.b64decode(str(face.get("emb") or ""))
                embedding = np.frombuffer(raw, dtype=np.float32)
            except Exception:
                continue
            if embedding.size != EMBEDDING_SIZE:
                continue
            embeddings.append(embedding.copy())
            # Arama çıktısında yalnızca bu alanlar kullanılıyor; bbox ve
            # det_score saklamak 31k kayıtta extra ~8 MB harcıyordu.
            metas.append(
                {
                    "file_id": str(row.get("file_id") or ""),
                    "name": str(row.get("name") or ""),
                    "path": str(row.get("path") or ""),
                    "width": int(row.get("width") or 0),
                    "height": int(row.get("height") or 0),
                }
            )
    return embeddings, metas


def _stack(
    embeddings: list[np.ndarray],
) -> np.ndarray:
    if not embeddings:
        return np.empty((0, EMBEDDING_SIZE), dtype=np.float32)
    matrix = np.vstack(embeddings).astype(np.float32, copy=False)
    embeddings.clear()
    return matrix


def fetch_matrix(db: D1Client, folder_key: str) -> tuple[np.ndarray, list[dict]]:
    """Tüm klasörü tarar. Yalnızca ilk matris oluşturulurken kullanılır."""
    embeddings: list[np.ndarray] = []
    metas: list[dict] = []
    last_id = ""
    release_pages = 0

    while True:
        rows = db.query(
            """
            SELECT file_id, name, path, width, height, status, faces
            FROM drive_face_index
            WHERE folder_key = ? AND file_id > ?
            ORDER BY file_id
            LIMIT ?
            """,
            (folder_key, last_id, _PAGE_SIZE),
        )
        if not rows:
            break
        page_embeddings, page_metas = _rows_to_embeddings(rows)
        embeddings.extend(page_embeddings)
        metas.extend(page_metas)

        last_id = str(rows[-1].get("file_id") or "")
        more = len(rows) >= _PAGE_SIZE and bool(last_id)
        del rows
        if release_pages % 4 == 0:
            release_memory()
        release_pages += 1
        if not more:
            break

    matrix = _stack(embeddings)
    release_memory()
    return matrix, metas


def update_matrix_from_changes(
    db: D1Client,
    folder_key: str,
    version: int,
    changed_file_ids: set[str] | list[str],
) -> None:
    """Incremental index bitiminde matrisi en az satır okumasıyla günceller.

    Mevcut matris BLOB'u (1 satır) okunur; yalnızca değişen dosyaların yüz
    satırları sorgulanır. Matris yoksa (ilk index/reindex) tam taramaya düşer.
    Yazma her zaman tek satırdır.
    """
    changed = {str(value) for value in changed_file_ids if value}
    loaded = load_matrix(db, folder_key, None)

    if loaded is None or not changed:
        if loaded is None:
            matrix, metas = fetch_matrix(db, folder_key)
        else:
            matrix, metas = loaded
        save_matrix(db, folder_key, version, matrix, metas)
        return

    old_matrix, old_metas = loaded
    remove = {
        index
        for index, meta in enumerate(old_metas)
        if str(meta.get("file_id") or "") in changed
    }
    keep_matrix = np.delete(old_matrix, list(remove), axis=0) if remove else old_matrix
    keep_metas = [meta for index, meta in enumerate(old_metas) if index not in remove]

    new_embeddings: list[np.ndarray] = []
    new_metas: list[dict] = []
    values = sorted(changed)
    for start in range(0, len(values), 80):
        chunk = values[start : start + 80]
        placeholders = ",".join("?" for _ in chunk)
        rows = db.query(
            f"""
            SELECT file_id, name, path, width, height, status, faces
            FROM drive_face_index
            WHERE folder_key = ? AND file_id IN ({placeholders})
            """,
            [folder_key, *chunk],
        )
        page_embeddings, page_metas = _rows_to_embeddings(rows)
        new_embeddings.extend(page_embeddings)
        new_metas.extend(page_metas)

    if new_embeddings:
        matrix = np.vstack([keep_matrix, _stack(new_embeddings)]).astype(
            np.float32, copy=False
        )
    else:
        matrix = keep_matrix
    save_matrix(db, folder_key, version, matrix, keep_metas + new_metas)


def public_and_version(db: D1Client, folder_key: str) -> tuple[bool, int]:
    """Tek D1 isteğinde yayın durumu + index versiyonu.

    Arama yolunda ayrı ayrı ``is_public_folder`` ve ``get_version``
    çağrıları iki HTTP isteği ve iki ayrı satır okumasıydı. Scalar subquery
    ikisini tek yanıtta birleştirir.
    """
    row = db.query_one(
        """
        SELECT
            EXISTS(SELECT 1 FROM events
                   WHERE folder_key = ? AND is_public = 1) AS is_public,
            (SELECT version FROM folder_index_versions
             WHERE folder_key = ? LIMIT 1) AS version
        """,
        (folder_key, folder_key),
    ) or {}
    return bool(row.get("is_public")), int(row.get("version") or 0)


def stats(db: D1Client, folder_key: str) -> dict[str, int]:
    row = db.query_one(
        """
        SELECT
            COUNT(*) AS images,
            COALESCE(SUM(json_array_length(faces)), 0) AS faces
        FROM drive_face_index
        WHERE folder_key = ?
        """,
        (folder_key,),
    )
    return {
        "images": int((row or {}).get("images") or 0),
        "faces": int((row or {}).get("faces") or 0),
    }


def file_ids(db: D1Client, folder_key: str, values: list[str]) -> list[str]:
    """Klasöre ait olduğu doğrulanmış dosya id'leri."""
    if not values:
        return []
    found: list[str] = []
    for start in range(0, len(values), 80):
        chunk = [str(v) for v in values[start : start + 80]]
        placeholders = ",".join("?" for _ in chunk)
        rows = db.query(
            f"""
            SELECT DISTINCT file_id FROM drive_face_index
            WHERE folder_key = ? AND file_id IN ({placeholders})
            """,
            [folder_key, *chunk],
        )
        found.extend(str(row["file_id"]) for row in rows if row.get("file_id"))
    return found
