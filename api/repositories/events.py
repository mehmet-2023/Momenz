from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..db import D1Client
from . import index as index_repo

_SELECT = """
    SELECT e.*,
           json_extract(d.meta, '$.folder_date') AS drive_uploaded_at,
           m.first_file_id AS first_file_id,
           (SELECT COUNT(*) FROM event_attendees a WHERE a.event_id = e.id)
               AS attendee_count,
           (SELECT COUNT(*) FROM event_attendees a
            WHERE a.event_id = e.id AND a.user_id = ?) AS attending_flag,
           COALESCE(
               NULLIF(json_extract(d.meta, '$.folder_count'), ''),
               m.images
           ) AS image_count,
           COALESCE(m.rows, 0) AS face_count
    FROM events e
    LEFT JOIN drive_folders d ON d.folder_key = e.folder_key
    LEFT JOIN folder_matrices m ON m.folder_key = e.folder_key
"""


def _date_label(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.strftime("%d %b %Y")
    except ValueError:
        return str(value)[:16]


def _to_out(row: dict, viewer_id: str = "") -> dict[str, Any]:
    folder_key = str(row.get("folder_key") or "")
    cover_id = str(row.get("cover_file_id") or row.get("first_file_id") or "")
    return {
        "id": str(row.get("id") or ""),
        "slug": str(row.get("slug") or ""),
        "title": str(row.get("title") or "Etkinlik"),
        "description": str(row.get("description") or ""),
        "drive_uploaded_at": row.get("drive_uploaded_at"),
        "date_label": _date_label(row.get("drive_uploaded_at")),
        "folder_key": folder_key,
        "owner_id": row.get("owner_id"),
        "cover_url": (
            f"/api/v1/public/folders/{folder_key}/photos/{cover_id}/thumb?size=320"
            if cover_id
            else None
        ),
        "image_count": int(row.get("image_count") or 0),
        "face_count": int(row.get("face_count") or 0),
        "attendee_count": int(row.get("attendee_count") or 0),
        "is_attending": bool(int(row.get("attending_flag") or 0)),
        "is_public": bool(int(row.get("is_public") or 0)),
        "is_owner": bool(viewer_id and str(row.get("owner_id") or "") == viewer_id),
        "created_at": row.get("created_at"),
    }


def list_all(
    db: D1Client,
    viewer_id: str = "",
    *,
    upcoming: bool = False,
    query: str | None = None,
    limit: int = 24,
    offset: int = 0,
    owner_id: str | None = None,
) -> list[dict]:
    where = ["e.is_public = 1"]
    params: list[Any] = [viewer_id]
    if owner_id:
        where.append("e.owner_id = ?")
        params.append(owner_id)
    if query:
        like = f"%{query.strip()}%"
        where.append("(e.title LIKE ? OR e.description LIKE ? OR e.slug LIKE ?)")
        params.extend([like, like, like])
    # Etkinlik tarihi artık Drive metadata'sından geliyor; "yaklaşan" filtresi yok.

    sql = _SELECT + " WHERE " + " AND ".join(where)
    # Drive yükleme tarihi (meta.folder_date) esas; sisteme eklenme tarihi
    # yalnızca Drive tarihi yoksa yedek olarak kullanılır. En yeni en üstte.
    sql += (
        " ORDER BY COALESCE(json_extract(d.meta, '$.folder_date'), e.created_at) DESC,"
        " e.created_at DESC"
    )
    sql += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return [_to_out(row, viewer_id) for row in db.query(sql, params)]


def count_all(
    db: D1Client,
    *,
    upcoming: bool = False,
    query: str | None = None,
    owner_id: str | None = None,
) -> int:
    where = ["e.is_public = 1"]
    params: list[Any] = []
    if owner_id:
        where.append("e.owner_id = ?")
        params.append(owner_id)
    if query:
        like = f"%{query.strip()}%"
        where.append("(e.title LIKE ? OR e.description LIKE ? OR e.slug LIKE ?)")
        params.extend([like, like, like])
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM events e WHERE " + " AND ".join(where), params
    )
    return int((row or {}).get("n") or 0)


def get_by_slug(db: D1Client, slug: str, viewer_id: str = "") -> dict | None:
    row = db.query_one(_SELECT + " WHERE e.slug = ? LIMIT 1", [viewer_id, slug])
    return _to_out(row, viewer_id) if row else None


def get_by_folder(db: D1Client, folder_key: str, viewer_id: str = "") -> dict | None:
    row = db.query_one(
        _SELECT + " WHERE e.folder_key = ? LIMIT 1", [viewer_id, folder_key]
    )
    return _to_out(row, viewer_id) if row else None


def is_public_folder(db: D1Client, folder_key: str) -> bool:
    row = db.query_one(
        "SELECT 1 FROM events WHERE folder_key = ? AND is_public = 1 LIMIT 1",
        (folder_key,),
    )
    return row is not None


def create(
    db: D1Client,
    *,
    event_id: str,
    slug: str,
    owner_id: str,
    folder_key: str,
    title: str,
    description: str,
) -> None:
    db.execute(
        """
        INSERT INTO events
            (id, slug, owner_id, folder_key, title, description,
             is_public, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        """,
        (
            event_id,
            slug,
            owner_id,
            folder_key,
            title,
            description,
        ),
    )
    # Arama tek matris satırını okuduğu için yayın bayrağını da orada tutuyoruz.
    index_repo.set_matrix_public(db, folder_key, True)


def join(db: D1Client, slug: str, user_id: str) -> bool:
    row = db.query_one("SELECT id FROM events WHERE slug = ? LIMIT 1", (slug,))
    if not row:
        return False
    db.execute(
        "INSERT OR IGNORE INTO event_attendees (event_id, user_id) VALUES (?, ?)",
        (row["id"], user_id),
    )
    return True


def leave(db: D1Client, slug: str, user_id: str) -> bool:
    row = db.query_one("SELECT id FROM events WHERE slug = ? LIMIT 1", (slug,))
    if not row:
        return False
    db.execute(
        "DELETE FROM event_attendees WHERE event_id = ? AND user_id = ?",
        (row["id"], user_id),
    )
    return True


def photos(
    db: D1Client, folder_key: str, limit: int = 24, files: list[dict] | None = None
) -> list[dict]:
    if files is None:
        files = index_repo.folder_files(db, folder_key)
    # Kopyala-sırala: çağıran taraf süreç içi cache'lenmiş listeyi paylaşabilir;
    # onu yerinde değiştirmek eşzamanlı isteklerde yarışa yol açar.
    ordered = sorted(files, key=lambda row: str(row.get("file_id") or ""))
    return [
        {
            "file_id": str(row.get("file_id") or ""),
            "name": str(row.get("name") or ""),
            "width": int(row.get("width") or 0),
            "height": int(row.get("height") or 0),
        }
        for row in ordered[:limit]
        if row.get("file_id")
    ]
