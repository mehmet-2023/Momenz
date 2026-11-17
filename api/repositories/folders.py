from __future__ import annotations

from typing import Any

from ..db import D1Client
from .common import dumps, loads


def list_for_user(db: D1Client, owner_id: str) -> list[dict]:
    rows = db.query(
        """
        SELECT d.folder_key, d.meta, d.updated_at,
               COUNT(f.file_id) AS image_count,
               COALESCE(SUM(json_array_length(f.faces)), 0) AS face_count
        FROM drive_folders d
        LEFT JOIN drive_face_index f ON f.folder_key = d.folder_key
        WHERE d.owner_id = ?
        GROUP BY d.folder_key, d.meta, d.updated_at
        ORDER BY d.updated_at DESC
        """,
        (owner_id,),
    )
    return [
        {
            "folder_key": str(row.get("folder_key") or ""),
            "meta": loads(row.get("meta"), {}) or {},
            "image_count": int(row.get("image_count") or 0),
            "face_count": int(row.get("face_count") or 0),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
    ]


def get_for_user(db: D1Client, owner_id: str, folder_key: str) -> dict | None:
    return db.query_one(
        """
        SELECT folder_key, meta, updated_at FROM drive_folders
        WHERE folder_key = ? AND owner_id = ? LIMIT 1
        """,
        (folder_key, owner_id),
    )


def exists_for_user(db: D1Client, owner_id: str, folder_key: str) -> bool:
    return get_for_user(db, owner_id, folder_key) is not None


def upsert(
    db: D1Client,
    owner_id: str,
    folder_key: str,
    meta: dict[str, Any],
) -> None:
    existing = get_for_user(db, owner_id, folder_key)
    merged = (loads(existing.get("meta"), {}) if existing else {}) or {}
    merged.update(meta or {})
    db.execute(
        """
        INSERT INTO drive_folders (folder_key, owner_id, meta, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT (folder_key) DO UPDATE SET
            meta = excluded.meta,
            owner_id = excluded.owner_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (folder_key, owner_id, dumps(merged)),
    )


def set_meta(db: D1Client, folder_key: str, key: str, value: str) -> None:
    db.execute(
        """
        UPDATE drive_folders
        SET meta = json_patch(meta, json_object(?, ?)),
            updated_at = CURRENT_TIMESTAMP
        WHERE folder_key = ?
        """,
        (key, str(value), folder_key),
    )


def delete(db: D1Client, owner_id: str, folder_key: str) -> bool:
    if not exists_for_user(db, owner_id, folder_key):
        return False
    db.batch(
        [
            {
                "sql": "DELETE FROM drive_face_index WHERE folder_key = ?",
                "params": [folder_key],
            },
            {
                "sql": "DELETE FROM folder_index_versions WHERE folder_key = ?",
                "params": [folder_key],
            },
            {
                "sql": "UPDATE jobs SET status = 'canceled', updated_at = CURRENT_TIMESTAMP WHERE folder_key = ? AND status IN ('queued','running')",
                "params": [folder_key],
            },
            {
                "sql": "DELETE FROM drive_folders WHERE folder_key = ? AND owner_id = ?",
                "params": [folder_key, owner_id],
            },
        ]
    )
    return True


def get_version(db: D1Client, folder_key: str) -> int:
    row = db.query_one(
        "SELECT version FROM folder_index_versions WHERE folder_key = ? LIMIT 1",
        (folder_key,),
    )
    return int((row or {}).get("version") or 0)


def bump_version(db: D1Client, folder_key: str) -> int:
    db.execute(
        """
        INSERT INTO folder_index_versions (folder_key, version, updated_at)
        VALUES (?, 1, CURRENT_TIMESTAMP)
        ON CONFLICT (folder_key) DO UPDATE SET
            version = folder_index_versions.version + 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (folder_key,),
    )
    return get_version(db, folder_key)


def find_folder_of_file(db: D1Client, file_id: str) -> str | None:
    row = db.query_one(
        "SELECT folder_key FROM drive_face_index WHERE file_id = ? LIMIT 1",
        (file_id,),
    )
    return str(row["folder_key"]) if row and row.get("folder_key") else None
