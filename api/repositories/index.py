from __future__ import annotations

import base64
import json
import zlib
from typing import Any

import numpy as np

from core.config import EMBEDDING_SIZE
from core.mem import release_memory

from ..db import D1Client

_QUANT = 127.0

# Sıkşturma bombası / bozuk BLOB savunması: bir satırdan çözülebilecek azami
# veri boyutu. Gerçek en büyük klasör ~5 MB sıkıştırılmış, ~25 MB açılmış.
_MAX_FILES_BYTES = 128 * 1024 * 1024
_MAX_METAS_BYTES = 64 * 1024 * 1024
_MAX_META_BYTES = 1024 * 1024
_MAX_EMB_BYTES = 1024  # 128 float32 -> 512 byte -> 684 base64 karakter

_MATRIX_TABLE_READY: set[int] = set()


class IndexDataError(ValueError):
    """Index BLOB'u bozuk, sınır aşımı veya kötü niyetli."""

_MATRIX_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS folder_matrices (
    folder_key TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 0,
    is_public INTEGER NOT NULL DEFAULT 0,
    matrix BLOB NOT NULL,
    metas BLOB NOT NULL,
    rows INTEGER NOT NULL DEFAULT 0,
    files BLOB,
    images INTEGER NOT NULL DEFAULT 0,
    done INTEGER NOT NULL DEFAULT 0,
    no_face INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    first_file_id TEXT,
    meta TEXT NOT NULL DEFAULT '{}',
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


# ---------------------------------------------------------------------------
# Sıkıştırılmış tek satır formatı
#
# matrix : int8 nicemlenmiş float32 vektörler (4x küçük), satır başına 128 byte
# metas  : zlib + kompakt JSON (arama için dosya başına tek meta)
# files  : zlib + kompakt JSON; embedding YOK, yalnızca dosya meta + yüz sayısı
#          (embedding'ler matrix'te tek kopya; eski format 105 MB'dı)
# Eski (float32 matrix / sıkıştırılmamış JSON) satırlar otomatik tanınır.
# ---------------------------------------------------------------------------


def _maybe_decompress(raw: Any, limit: int) -> bytes:
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    if isinstance(raw, (bytes, bytearray)):
        value = bytes(raw)
    else:
        return b""
    if not value:
        return b""
    if len(value) > limit:
        raise IndexDataError("Index alanı boyut sınırını aştı.")
    if value[:1] != b"\x78":  # zlib başlığı yok: eski sıkıştırılmamış JSON
        if len(value) > limit:
            raise IndexDataError("Index alanı boyut sınırını aştı.")
        return value
    decompressor = zlib.decompressobj()
    try:
        payload = decompressor.decompress(value, limit + 1)
    except zlib.error as exc:
        raise IndexDataError("Bozuk zlib verisi.") from exc
    if len(payload) > limit or not decompressor.eof:
        raise IndexDataError("Sıkıştırılmış index boyut sınırını aştı.")
    return payload


def _encode_json(value: Any) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return zlib.compress(payload, 6)


def _decode_json(raw: Any, limit: int = _MAX_METAS_BYTES) -> Any:
    payload = _maybe_decompress(raw, limit)
    if not payload:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def _quantize(matrix: np.ndarray) -> bytes:
    values = np.clip(np.round(matrix * _QUANT), -127, 127).astype(np.int8)
    return values.tobytes()


def _dequantize(raw: bytes, count: int) -> np.ndarray:
    size = count * EMBEDDING_SIZE
    if len(raw) == size * 4:  # eski float32 format
        return np.frombuffer(raw, dtype=np.float32).reshape(count, EMBEDDING_SIZE)
    q = np.frombuffer(raw[:size], dtype=np.int8)
    if q.size != size:
        raise ValueError("Matris BLOB boyutu satır sayısıyla uyuşmuyor.")
    return q.reshape(count, EMBEDDING_SIZE).astype(np.float32) / _QUANT


def _encode_files(files: list[dict]) -> bytes:
    """Embedding'siz kompakt dosya kayıtları: sadece meta + yüz sayısı."""
    compact = [
        {
            "i": str(row.get("file_id") or ""),
            "n": str(row.get("name") or ""),
            "p": str(row.get("path") or ""),
            "w": int(row.get("width") or 0),
            "h": int(row.get("height") or 0),
            "s": str(row.get("status") or "done"),
            "e": row.get("error"),
            "t": row.get("claimed_at"),
            "c": len(row.get("faces") or []),
        }
        for row in files
        if str(row.get("file_id") or "")
    ]
    return _encode_json(compact)


def _decode_files(
    raw: Any,
    matrix: np.ndarray | None = None,
    *,
    with_faces: bool = True,
    limit: int = _MAX_FILES_BYTES,
) -> list[dict]:
    items = _decode_json(raw, limit)
    if not isinstance(items, list):
        return []
    output: list[dict] = []
    offset = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        file_id = str(item.get("i") or item.get("file_id") or "")
        record = {
            "file_id": file_id,
            "name": str(item.get("n") or item.get("name") or ""),
            "path": str(item.get("p") or item.get("path") or ""),
            "width": int(item.get("w") or item.get("width") or 0),
            "height": int(item.get("h") or item.get("height") or 0),
            "status": str(item.get("s") or item.get("status") or "done"),
            "error": item.get("e", item.get("error")),
            "faces": [],
        }
        if item.get("t") is not None:
            record["claimed_at"] = item["t"]
        if with_faces:
            if isinstance(item.get("faces"), list):  # eski format: gömülü embedding
                record["faces"] = item["faces"]
            else:
                count = max(0, int(item.get("c") or 0))
                if matrix is not None and count:
                    block = matrix[offset : offset + count]
                    record["faces"] = [
                        {
                            "emb": base64.b64encode(
                                np.ascontiguousarray(vector, dtype=np.float32).tobytes()
                            ).decode("ascii")
                        }
                        for vector in block
                    ]
                offset += count
        output.append(record)
    return output


def load_index_row(
    db: D1Client, folder_key: str
) -> tuple[int, list[dict], dict] | None:
    """Tam index satırını TEK okumayla döndürür: (sürüm, dosyalar, meta).

    Dönen dosya kayıtlarındaki yüz vektörleri matristen yeniden kurulur;
    worker bellekten patchleyip aynı satırı TEK yazımda geri yazar.
    """
    row = db.query_one(
        """
        SELECT version, matrix, metas, rows, files, meta
        FROM folder_matrices WHERE folder_key = ? LIMIT 1
        """,
        (folder_key,),
    )
    if not row or row.get("files") is None:
        return None
    try:
        matrix = _dequantize(bytes(row.get("matrix") or b""), int(row.get("rows") or 0))
        files = _decode_files(row["files"], matrix)
        meta = _decode_json(row.get("meta"), _MAX_META_BYTES) or {}
    except IndexDataError:
        # Bozuk/şişirilmiş satırı asla geri yazmayacak şekilde yok say.
        return None
    except ValueError:
        return None
    if not isinstance(meta, dict):
        meta = {}
    return int(row.get("version") or 0), files, meta


def save_index_row(
    db: D1Client,
    folder_key: str,
    version: int,
    files: list[dict],
    meta: dict | None = None,
) -> None:
    """Klasörün tam index'ini + türetilmiş matrisi TEK satır olarak yazar.

    Embedding'ler yalnızca ``matrix`` alanında int8 olarak tutulur; ``files``
    alanında yinelenmez. Matris ve metas bu dosyalardan türetilir; arama aynı
    satırdan okumaya devam eder. ``is_public`` UPDATE'de güncellenmez.
    """
    ensure_folder_matrices(db)
    records = [dict(item) for item in files if str(item.get("file_id") or "")]

    embeddings: list[np.ndarray] = []
    metas: list[dict] = []
    counts = {"done": 0, "no_face": 0, "error": 0}
    first_file_id = ""
    for record in records:
        file_id = str(record.get("file_id") or "")
        status = str(record.get("status") or "done")
        if status in counts:
            counts[status] += 1
        if not first_file_id:
            first_file_id = file_id
        if status != "done":
            continue
        for face in record.get("faces") or []:
            try:
                encoded = str(face.get("emb") or "")
                if len(encoded) > _MAX_EMB_BYTES:
                    continue
                raw = base64.b64decode(encoded)
                embedding = np.frombuffer(raw, dtype=np.float32)
            except Exception:
                continue
            if embedding.size != EMBEDDING_SIZE:
                continue
            embeddings.append(embedding.copy())
            metas.append(
                {
                    "file_id": file_id,
                    "name": str(record.get("name") or ""),
                    "path": str(record.get("path") or ""),
                    "width": int(record.get("width") or 0),
                    "height": int(record.get("height") or 0),
                }
            )

    matrix = np.vstack(embeddings).astype(np.float32) if embeddings else np.empty(
        (0, EMBEDDING_SIZE), dtype=np.float32
    )
    # Satır ilk kez oluşturuluyorsa yayın bayrağını events'ten al; sonraki
    # yazımlarda set_matrix_public() tarafından güncellenen değeri koru.
    is_public = folder_is_public(db, folder_key)
    db.execute(
        """
        INSERT INTO folder_matrices
            (folder_key, version, is_public, matrix, metas, rows, files, images,
             done, no_face, errors, first_file_id, meta, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT (folder_key) DO UPDATE SET
            version = excluded.version,
            matrix = excluded.matrix,
            metas = excluded.metas,
            rows = excluded.rows,
            files = excluded.files,
            images = excluded.images,
            done = excluded.done,
            no_face = excluded.no_face,
            errors = excluded.errors,
            first_file_id = excluded.first_file_id,
            meta = excluded.meta,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            folder_key,
            int(version),
            1 if is_public else 0,
            _quantize(matrix),
            _encode_json(metas),
            int(matrix.shape[0]),
            _encode_files(records),
            len(records),
            counts["done"],
            counts["no_face"],
            counts["error"],
            first_file_id,
            json.dumps(meta or {}, ensure_ascii=False, separators=(",", ":")),
        ),
    )


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
    """Eski uyumluluk yazımı: sıkıştırılmış tek satır formatına yazar."""
    ensure_folder_matrices(db)
    if is_public is None:
        is_public = folder_is_public(db, folder_key)
    array = np.ascontiguousarray(matrix, dtype=np.float32)
    if array.ndim != 2 or array.shape[1] != EMBEDDING_SIZE:
        raise ValueError("Matris boyutu EMBEDDING_SIZE ile uyuşmuyor.")
    if array.shape[0] != len(metas):
        raise ValueError("Matris satır sayısı metadata sayısı ile uyuşmuyor.")
    db.execute(
        """
        INSERT INTO folder_matrices
            (folder_key, version, is_public, matrix, metas, rows, files, images)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            _quantize(array),
            _encode_json(metas),
            int(array.shape[0]),
            _encode_json([]),
            int(array.shape[0]),
        ),
    )


def _decode_matrix_row(row: dict) -> tuple[np.ndarray, list[dict]] | None:
    try:
        count = int(row.get("rows") or 0)
        matrix = _dequantize(bytes(row.get("matrix") or b""), count)
        metas = _decode_json(row.get("metas"))
        if not isinstance(metas, list) or len(metas) != count:
            return None
        return matrix, metas
    except (TypeError, ValueError, zlib.error):
        return None


def load_matrix(
    db: D1Client, folder_key: str, version: int | None
) -> tuple[np.ndarray, list[dict]] | None:
    """Sürüm eşleşirse matrisi tek satırdan okur, aksi halde ``None``."""
    row = db.query_one(
        "SELECT version, matrix, metas, rows FROM folder_matrices WHERE folder_key = ? LIMIT 1",
        (folder_key,),
    )
    if not row:
        return None
    if version is not None and int(row.get("version") or 0) != int(version):
        return None
    return _decode_matrix_row(row)


def public_version_matrix(
    db: D1Client, folder_key: str, owner_id: str | None = None
) -> tuple[bool, int, tuple[np.ndarray, list[dict]] | None]:
    """Arama için gereken her şeyi TEKE okumayla döndürür.

    Yetkisiz kullanıcıya matris BLOB'u hiç indirilmez: izin kontrolü SQL'in
    içinde yapılır. Böylece kötü niyetli biri özel bir klasörün folder_key'ini
    bilse bile 5 MB'lık matrisi sunucuya çektiremez.
    """
    viewer = str(owner_id or "")
    allowed = """(
        m.is_public = 1 OR EXISTS(
            SELECT 1 FROM drive_folders d
            WHERE d.folder_key = m.folder_key AND d.owner_id = ?
        )
    )"""
    row = db.query_one(
        f"""
        SELECT m.is_public, m.version, m.rows,
               CASE WHEN {allowed} THEN m.matrix END AS matrix,
               CASE WHEN {allowed} THEN m.metas END AS metas
        FROM folder_matrices m WHERE m.folder_key = ? LIMIT 1
        """,
        (viewer, viewer, folder_key),
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
                encoded = str(face.get("emb") or "")
                if len(encoded) > _MAX_EMB_BYTES:
                    continue
                raw = base64.b64decode(encoded)
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
                }
            )
    return embeddings, metas


def _stack(embeddings: list[np.ndarray]) -> np.ndarray:
    if not embeddings:
        return np.empty((0, EMBEDDING_SIZE), dtype=np.float32)
    matrix = np.vstack(embeddings).astype(np.float32, copy=False)
    embeddings.clear()
    return matrix


def folder_files(db: D1Client, folder_key: str) -> list[dict]:
    """Klasörün dosya meta'larını TEK satırdan okur (yüz vektörü ÇEKMEZ)."""
    row = db.query_one(
        "SELECT files FROM folder_matrices WHERE folder_key = ? LIMIT 1",
        (folder_key,),
    )
    return _decode_files((row or {}).get("files"), with_faces=False)


def fetch_matrix(db: D1Client, folder_key: str) -> tuple[np.ndarray, list[dict]]:
    """Arama matrisini doğrudan tek satırdan okur (fallback)."""
    loaded = load_matrix(db, folder_key, None)
    if loaded is not None:
        return loaded
    release_memory()
    return np.empty((0, EMBEDDING_SIZE), dtype=np.float32), []


def update_matrix_from_changes(
    db: D1Client,
    folder_key: str,
    version: int,
    changed_file_ids: set[str] | list[str] | None = None,
) -> None:
    """Uyumluluk sarmalayıcısı: mevcut tek satırı yeni sürümle yeniden yazar."""
    loaded = load_index_row(db, folder_key)
    if loaded is None:
        return
    _, files, meta = loaded
    save_index_row(db, folder_key, version, files, meta)


def public_and_version(db: D1Client, folder_key: str) -> tuple[bool, int]:
    """Yayın durumu + sürümü tek satırdan okur."""
    row = db.query_one(
        "SELECT is_public, version FROM folder_matrices WHERE folder_key = ? LIMIT 1",
        (folder_key,),
    ) or {}
    return bool(row.get("is_public")), int(row.get("version") or 0)


def index_stats(db: D1Client, folder_key: str) -> dict[str, int]:
    """Klasör istatistiklerini tek satırdan okur (tam tarama yok)."""
    row = db.query_one(
        "SELECT images, done, no_face, errors, rows FROM folder_matrices WHERE folder_key = ? LIMIT 1",
        (folder_key,),
    ) or {}
    return {
        "images": int(row.get("images") or 0),
        "done": int(row.get("done") or 0),
        "no_face": int(row.get("no_face") or 0),
        "errors": int(row.get("errors") or 0),
        "faces": int(row.get("rows") or 0),
    }


def stats(db: D1Client, folder_key: str) -> dict[str, int]:
    data = index_stats(db, folder_key)
    return {"images": data["images"], "faces": data["faces"]}


def file_ids(db: D1Client, folder_key: str, values: list[str]) -> list[str]:
    """Klasöre ait olduğu doğrulanmış dosya id'leri (tek satırdan)."""
    if not values:
        return []
    wanted = {str(value) for value in values if value}
    return [
        str(row.get("file_id") or "")
        for row in folder_files(db, folder_key)
        if str(row.get("file_id") or "") in wanted
    ]


def public_files(db: D1Client, folder_key: str) -> tuple[bool, list[dict]]:
    """Yayın bayrağı + dosya meta'ları TEK satır okumayla döner."""
    row = db.query_one(
        "SELECT is_public, files FROM folder_matrices WHERE folder_key = ? LIMIT 1",
        (folder_key,),
    ) or {}
    return bool(row.get("is_public")), _decode_files(row.get("files"), with_faces=False)


def public_file_ids(
    db: D1Client, folder_key: str, values: list[str]
) -> tuple[bool, list[str]]:
    """Yayın bayrağı + doğrulanmış dosya id'leri TEK satır okumayla döner.

    Thumbnail uçları eskiden ``events`` ve ``folder_matrices`` için iki ayrı
    sorgu yapıyordu; görsel başına okuma sayısını yarıya indirir.
    """
    if not values:
        return False, []
    row = db.query_one(
        "SELECT is_public, files FROM folder_matrices WHERE folder_key = ? LIMIT 1",
        (folder_key,),
    ) or {}
    wanted = {str(value) for value in values if value}
    found = [
        str(item.get("file_id") or "")
        for item in _decode_files(row.get("files"), with_faces=False)
        if str(item.get("file_id") or "") in wanted
    ]
    return bool(row.get("is_public")), found
