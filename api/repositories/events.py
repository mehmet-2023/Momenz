from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..db import D1Client

_SELECT = """
    SELECT e.*,
           (SELECT file_id FROM drive_face_index
            WHERE folder_key = e.folder_key ORDER BY file_id LIMIT 1) AS first_file_id,
           (SELECT COUNT(*) FROM event_attendees a WHERE a.event_id = e.id)
               AS attendee_count,
           (SELECT COUNT(*) FROM event_attendees a
            WHERE a.event_id = e.id AND a.user_id = ?) AS attending_flag,
           (SELECT COUNT(DISTINCT f.file_id) FROM drive_face_index f
            WHERE f.folder_key = e.folder_key) AS image_count,
           (SELECT COALESCE(SUM(json_array_length(f.faces)), 0) FROM drive_face_index f
            WHERE f.folder_key = e.folder_key) AS face_count
    FROM events e
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
        "location": str(row.get("location") or ""),
        "event_date": row.get("event_date"),
        "date_label": _date_label(row.get("event_date")),
        "folder_key": folder_key,
        "owner_id": row.get("owner_id"),
        "cover_url": (
            f"/api/v1/public/folders/{folder_key}/photos/{cover_id}/thumb?size=640"
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
        where.append("(e.title LIKE ? OR e.location LIKE ? OR e.description LIKE ?)")
        params.extend([like, like, like])
    if upcoming:
        where.append("(e.event_date IS NULL OR e.event_date >= date('now'))")

    sql = _SELECT + " WHERE " + " AND ".join(where)
    sql += " ORDER BY e.event_date IS NULL, e.event_date ASC, e.created_at DESC"
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
        where.append("(e.title LIKE ? OR e.location LIKE ? OR e.description LIKE ?)")
        params.extend([like, like, like])
    if upcoming:
        where.append("(e.event_date IS NULL OR e.event_date >= date('now'))")
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
    location: str,
    event_date: str | None,
) -> None:
    db.execute(
        """
        INSERT INTO events
            (id, slug, owner_id, folder_key, title, description,
             location, event_date, is_public, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        """,
        (
            event_id,
            slug,
            owner_id,
            folder_key,
            title,
            description,
            location,
            event_date,
        ),
    )


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


def photos(db: D1Client, folder_key: str, limit: int = 24) -> list[dict]:
    rows = db.query(
        """
        SELECT file_id, name, width, height FROM drive_face_index
        WHERE folder_key = ?
        ORDER BY file_id LIMIT ?
        """,
        (folder_key, limit),
    )
    return [
        {
            "file_id": str(row.get("file_id") or ""),
            "name": str(row.get("name") or ""),
            "width": int(row.get("width") or 0),
            "height": int(row.get("height") or 0),
        }
        for row in rows
        if row.get("file_id")
    ]
