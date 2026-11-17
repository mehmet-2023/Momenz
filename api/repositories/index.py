from __future__ import annotations

import base64
import json
from typing import Any

import numpy as np

from core.config import EMBEDDING_SIZE

from ..db import D1Client

_PAGE_SIZE = 4000


def fetch_matrix(db: D1Client, folder_key: str) -> tuple[np.ndarray, list[dict]]:
    """D1'deki yüz embedding'lerini aranabilir numpy matrisine çevirir.

    ``core.pg_index_store.PgIndexStore.load_matrix`` ile aynı çıktıyı verir;
    farkı veriyi FastAPI katmanında, versiyon kontrollü cache ile üretmesidir.
    """
    embeddings: list[np.ndarray] = []
    metas: list[dict] = []
    last_id = ""

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

        last_id = str(rows[-1].get("file_id") or "")
        if len(rows) < _PAGE_SIZE or not last_id:
            break

    if not embeddings:
        return np.empty((0, EMBEDDING_SIZE), dtype=np.float32), []
    return np.vstack(embeddings).astype(np.float32), metas


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
