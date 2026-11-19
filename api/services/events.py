from __future__ import annotations

import re
import threading
import time
import unicodedata

from ..db import D1Client
from ..errors import NotFound
from ..repositories import events as repo
from ..schemas import (
    EventCreateIn,
    EventListOut,
    EventOut,
    EventPhotoListOut,
    EventPhotoOut,
)
from ..security import new_id
from . import folders as folder_service

# Her ana sayfa açılışında aynı 5 etkinlik için tekrar tekrar satır okunmasın.
# Yalnızca anonim/genel liste cache'lenir; kullanıcıya özel is_attending /
# is_owner alanları içerdiği için viewer'lı istekler cache'e girmez.
_events_cache: dict[tuple[str, int, int], tuple[float, "EventListOut"]] = {}
_events_cache_lock = threading.Lock()
_EVENTS_CACHE_TTL = 30.0


def invalidate_events_cache() -> None:
    with _events_cache_lock:
        _events_cache.clear()


def _slug(title: str) -> str:
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return f"{(text or 'etkinlik')[:48]}-{new_id()[:6]}"


def list_events(
    db: D1Client,
    viewer_id: str = "",
    *,
    upcoming: bool = False,
    query: str | None = None,
    limit: int = 24,
    offset: int = 0,
) -> EventListOut:
    key = None if viewer_id else (query or "", limit, offset)
    if key is not None:
        with _events_cache_lock:
            hit = _events_cache.get(key)
            if hit and time.monotonic() - hit[0] < _EVENTS_CACHE_TTL:
                return hit[1]

    items = repo.list_all(
        db,
        viewer_id,
        upcoming=upcoming,
        query=query,
        limit=limit,
        offset=offset,
    )
    result = EventListOut(
        items=[EventOut(**item) for item in items],
        total=repo.count_all(db, upcoming=upcoming, query=query),
    )
    if key is not None:
        with _events_cache_lock:
            _events_cache[key] = (time.monotonic(), result)
    return result


def my_events(db: D1Client, owner_id: str) -> EventListOut:
    items = repo.list_all(db, owner_id, owner_id=owner_id, limit=100)
    return EventListOut(items=[EventOut(**item) for item in items], total=len(items))


def get_event(db: D1Client, slug: str, viewer_id: str = "") -> EventOut:
    row = repo.get_by_slug(db, slug, viewer_id)
    if not row or not row.get("is_public", True):
        raise NotFound("Etkinlik bulunamadı.")
    return EventOut(**row)


def create_event(
    db: D1Client, owner_id: str, payload: EventCreateIn
) -> tuple[EventOut, str]:
    folder, job_id = folder_service.create_folder(
        db,
        owner_id,
        folder_service.FolderCreateIn(
            url=payload.url,
            include_subfolders=payload.include_subfolders,
        ),
    )
    # Başlık Drive klasörünün adından gelir; kullanıcı bir şey yazmaz.
    title = (folder.title or "").strip() or "Etkinlik"
    repo.create(
        db,
        event_id=new_id(),
        slug=_slug(title),
        owner_id=owner_id,
        folder_key=folder.key,
        title=title,
        description="",
    )
    created = repo.get_by_folder(db, folder.key, owner_id)
    if not created:
        raise RuntimeError("Etkinlik oluşturulamadı.")
    invalidate_events_cache()
    return EventOut(**created), job_id


def join_event(db: D1Client, slug: str, user_id: str) -> bool:
    if not repo.join(db, slug, user_id):
        raise NotFound("Etkinlik bulunamadı.")
    return True


def leave_event(db: D1Client, slug: str, user_id: str) -> bool:
    if not repo.leave(db, slug, user_id):
        raise NotFound("Etkinlik bulunamadı.")
    return True


def event_photos(
    db: D1Client, folder_key: str, limit: int = 24, files: list[dict] | None = None
) -> EventPhotoListOut:
    rows = repo.photos(db, folder_key, limit, files=files)
    return EventPhotoListOut(
        items=[
            EventPhotoOut(
                file_id=row["file_id"],
                name=row["name"],
                thumb_url=(
                    f"/api/v1/public/folders/{folder_key}/photos/{row['file_id']}/thumb?size=320"
                ),
                width=row["width"],
                height=row["height"],
            )
            for row in rows
        ],
        total=len(rows),
    )
