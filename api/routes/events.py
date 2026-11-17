from __future__ import annotations

import hashlib
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response, status

from core.image_utils import encode_jpeg_bytes

from ..config import Settings, get_settings
from ..db import D1Client
from ..deps import get_db, optional_user, require_user
from ..errors import Forbidden, NotFound
from ..repositories import events as repo
from ..schemas import (
    EventCreateIn,
    EventListOut,
    EventOut,
    EventPhotoListOut,
    MessageOut,
)
from ..services import events as service

router = APIRouter(prefix="/events", tags=["events"])
public_router = APIRouter(prefix="/public", tags=["public"])


@router.get("", response_model=EventListOut)
def list_events(
    upcoming: bool = Query(default=False),
    category: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: D1Client = Depends(get_db),
    viewer=Depends(optional_user),
) -> EventListOut:
    return service.list_events(
        db,
        viewer.id if viewer else "",
        upcoming=upcoming,
        category=category,
        query=q,
        limit=limit,
        offset=offset,
    )


@router.get("/mine", response_model=EventListOut)
def my_events(
    db: D1Client = Depends(get_db), user=Depends(require_user)
) -> EventListOut:
    return service.my_events(db, user.id)


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: EventCreateIn,
    response: Response,
    db: D1Client = Depends(get_db),
    user=Depends(require_user),
) -> EventOut:
    event, job_id = service.create_event(db, user.id, payload)
    response.headers["X-Job-ID"] = job_id
    return event


@router.get("/{slug}", response_model=EventOut)
def get_event(
    slug: str,
    db: D1Client = Depends(get_db),
    viewer=Depends(optional_user),
) -> EventOut:
    return service.get_event(db, slug, viewer.id if viewer else "")


@router.post("/{slug}/join", response_model=MessageOut)
def join_event(
    slug: str, db: D1Client = Depends(get_db), user=Depends(require_user)
) -> MessageOut:
    service.join_event(db, slug, user.id)
    return MessageOut(message="Etkinliğe katıldın.")


@router.delete("/{slug}/join", response_model=MessageOut)
def leave_event(
    slug: str, db: D1Client = Depends(get_db), user=Depends(require_user)
) -> MessageOut:
    service.leave_event(db, slug, user.id)
    return MessageOut(message="Etkinlikten ayrıldın.")


@router.get("/{slug}/photos", response_model=EventPhotoListOut)
def event_photos(
    slug: str,
    limit: int = Query(default=24, ge=1, le=60),
    db: D1Client = Depends(get_db),
) -> EventPhotoListOut:
    event = repo.get_by_slug(db, slug)
    if not event:
        raise NotFound("Etkinlik bulunamadı.")
    return service.event_photos(db, event["folder_key"], limit)


# ---------------------------------------------------------- public thumbnails
def _thumb_cache_path(settings: Settings, file_id: str, size: int) -> Path:
    digest = hashlib.sha1(f"{file_id}:{size}".encode("utf-8")).hexdigest()
    return Path(settings.thumb_cache_dir) / f"{digest[:2]}" / f"{digest}.jpg"


@public_router.get("/folders/{folder_key}/photos")
def public_photos(
    folder_key: str,
    limit: int = Query(default=24, ge=1, le=60),
    db: D1Client = Depends(get_db),
) -> EventPhotoListOut:
    if not repo.is_public_folder(db, folder_key):
        raise Forbidden("Bu klasör herkese açık değil.")
    return service.event_photos(db, folder_key, limit)


@public_router.get("/folders/{folder_key}/photos/{file_id}/thumb")
def public_thumb(
    folder_key: str,
    file_id: str,
    size: int = Query(default=384, ge=64, le=1024),
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not repo.is_public_folder(db, folder_key):
        raise Forbidden("Bu klasör herkese açık değil.")
    allowed = {item["file_id"] for item in repo.photos(db, folder_key, 500)}
    if file_id not in allowed:
        raise NotFound("Fotoğraf bu etkinlikte bulunamadı.")

    path = _thumb_cache_path(settings, file_id, size)
    if path.exists() and (time.time() - path.stat().st_mtime) < settings.thumb_cache_ttl_seconds:
        return Response(path.read_bytes(), media_type="image/jpeg")

    from ..services.drive import get_drive_client

    image = get_drive_client(settings).fetch_image(file_id, size)
    if image is None:
        raise NotFound("Önizleme alınamadı.")
    data = encode_jpeg_bytes(image, quality=80)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return Response(data, media_type="image/jpeg")
