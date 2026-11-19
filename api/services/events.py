from __future__ import annotations

import re
import threading
import time
import unicodedata

from core.config import DEFAULT_THUMB_SIZE, folder_key as make_folder_key
from core.drive import parse_drive_folder_url

from ..db import D1Client
from ..errors import AppError, Conflict, Forbidden, NotFound, UpstreamError
from ..repositories import events as repo
from ..schemas import (
    EventCreateIn,
    EventDriveIn,
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


def _folder_key(url: str, include_subfolders: bool) -> str:
    try:
        folder_id, resource_key = parse_drive_folder_url(url)
    except Exception as exc:
        raise UpstreamError(f"Drive klasör linki okunamadı: {exc}") from exc
    return make_folder_key(
        folder_id, resource_key, include_subfolders, DEFAULT_THUMB_SIZE
    )


def _duplicate_event(
    db: D1Client, key: str, owner_id: str, exclude_id: str = ""
) -> dict | None:
    existing = repo.get_by_folder(db, key, owner_id)
    if existing and str(existing.get("id") or "") != exclude_id:
        return existing
    return None


def create_event(
    db: D1Client, owner_id: str, payload: EventCreateIn
) -> tuple[EventOut, str]:
    url = (payload.url or "").strip()
    description = (payload.description or "").strip()

    if url:
        key = _folder_key(url, payload.include_subfolders)
        existing = _duplicate_event(db, key, owner_id)
        if existing:
            if existing.get("is_owner"):
                raise Conflict(
                    f"Bu Drive klasörü zaten “{existing['title']}” etkinliği "
                    "olarak kayıtlı."
                )
            raise Conflict("Bu Drive klasörü zaten başka bir etkinliğe bağlı.")

        folder, job_id = folder_service.create_folder(
            db,
            owner_id,
            folder_service.FolderCreateIn(
                url=url,
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
            description=description,
            event_date=payload.event_date,
        )
        created = repo.get_by_folder(db, folder.key, owner_id)
        if not created:
            raise RuntimeError("Etkinlik oluşturulamadı.")
        invalidate_events_cache()
        return EventOut(**created), job_id

    # Drive henüz yüklenmedi: klasör anahtarı yerine geçici bir anahtar
    # kullanılır. Fotoğraflar hazır olunca sahibi Drive linkini bağlar.
    title = (payload.title or "").strip()
    if not title:
        raise AppError("Drive linki yoksa etkinlik adı gerekli.")
    pending_key = f"pending-{new_id()}"
    repo.create(
        db,
        event_id=new_id(),
        slug=_slug(title),
        owner_id=owner_id,
        folder_key=pending_key,
        title=title,
        description=description,
        event_date=payload.event_date,
    )
    created = repo.get_by_folder(db, pending_key, owner_id)
    if not created:
        raise RuntimeError("Etkinlik oluşturulamadı.")
    invalidate_events_cache()
    return EventOut(**created), ""


def attach_drive(
    db: D1Client, owner_id: str, slug: str, payload: EventDriveIn
) -> tuple[EventOut, str]:
    event = repo.get_by_slug(db, slug, owner_id)
    if not event:
        raise NotFound("Etkinlik bulunamadı.")
    if str(event.get("owner_id") or "") != owner_id:
        raise Forbidden("Bu etkinliğe Drive bağlama iznin yok.")
    if not event.get("drive_pending"):
        raise Conflict("Bu etkinliğe zaten bir Drive klasörü bağlı.")

    url = payload.url.strip()
    key = _folder_key(url, payload.include_subfolders)
    existing = _duplicate_event(db, key, owner_id, exclude_id=str(event["id"]))
    if existing:
        if existing.get("is_owner"):
            raise Conflict(
                f"Bu Drive klasörü zaten “{existing['title']}” etkinliği "
                "olarak kayıtlı."
            )
        raise Conflict("Bu Drive klasörü zaten başka bir etkinliğe bağlı.")

    folder, job_id = folder_service.create_folder(
        db,
        owner_id,
        folder_service.FolderCreateIn(
            url=url,
            include_subfolders=payload.include_subfolders,
        ),
    )
    if not repo.attach_folder(db, str(event["id"]), owner_id, folder.key):
        raise Conflict("Drive bağlanamadı; etkinlik durumu değişmiş olabilir.")

    invalidate_events_cache()
    updated = repo.get_by_slug(db, slug, owner_id)
    if not updated:
        raise RuntimeError("Etkinlik güncellenemedi.")
    return EventOut(**updated), job_id


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
