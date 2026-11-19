from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from core.image_utils import encode_jpeg_bytes
from core.mem import release_memory
from core.zip_stream import stream_zip

from ..config import Settings, get_settings
from ..db import D1Client
from ..deps import get_db, optional_user, require_user
from ..errors import Forbidden, NotFound
from ..repositories import events as repo
from ..repositories import index as index_repo
from ..schemas import (
    BulkDownloadIn,
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
    viewer=Depends(optional_user),
) -> EventPhotoListOut:
    event = repo.get_by_slug(db, slug)
    if not event:
        raise NotFound("Etkinlik bulunamadı.")
    if not event.get("is_public", True) and (
        not viewer or str(event.get("owner_id") or "") != str(viewer.id)
    ):
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
    size: int = Query(default=320, ge=64, le=2048),
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not repo.is_public_folder(db, folder_key):
        raise Forbidden("Bu klasör herkese açık değil.")
    # Eski linklerdeki büyük boyut isteklerini küçük önizlemeye sabitle.
    size = min(size, 512)
    # 20.000+ fotoğraf içinde doğrudan ID sorgusu: ilk 500'e bakmak eşleşen
    # fotoğrafları yanlışlıkla "bulunamadı" yapıyordu.
    if not index_repo.file_ids(db, folder_key, [file_id]):
        raise NotFound("Fotoğraf bu etkinlikte bulunamadı.")

    path = _thumb_cache_path(settings, file_id, size)
    if path.exists() and (time.time() - path.stat().st_mtime) < settings.thumb_cache_ttl_seconds:
        return Response(
            path.read_bytes(),
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800"},
        )

    from ..services.drive import get_drive_client

    image = get_drive_client(settings).fetch_image(file_id, size)
    if image is None:
        raise NotFound("Önizleme alınamadı.")
    data = encode_jpeg_bytes(image, quality=78)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return Response(
        data,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800"},
    )


@public_router.post("/folders/{folder_key}/photos/download.zip")
def public_photos_zip(
    folder_key: str,
    payload: BulkDownloadIn,
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Eşleşen fotoğrafları seçilen çözünürlükte ZIP olarak indir."""
    if not repo.is_public_folder(db, folder_key):
        raise Forbidden("Bu klasör herkese açık değil.")
    # Kullanıcıya ait olmayan dosya ID'leriyle klassörü geçmeyi engelle.
    ids = index_repo.file_ids(db, folder_key, payload.file_ids)
    if not ids:
        raise NotFound("İndirilecek fotoğraf bulunamadı.")

    from ..services.drive import get_drive_client

    client = get_drive_client(settings)
    size = min(max(payload.size, 320), 2048)

    def images():
        from concurrent.futures import ThreadPoolExecutor

        def fetch(file_id: str):
            try:
                image = client.fetch_image(file_id, size)
                if image is None:
                    return None
                return f"{file_id}.jpg", encode_jpeg_bytes(image, quality=82)
            except Exception:
                # Tek bir bozuk dosya tüm indirmeyi bozmasın.
                return None

        # Drive isteklerini küçük partiler halinde paralelleştir: 200 dosyalı
        # bir ZIP tekthread'de Render/Vercel proxy zaman aşımına giriyordu.
        # Parti başına en fazla 16 görsel RAM'de tutulur, akış sırası korunur.
        for start in range(0, len(ids), 16):
            with ThreadPoolExecutor(max_workers=4) as pool:
                for item in pool.map(fetch, ids[start : start + 16]):
                    if item is not None:
                        yield item

    def generate():
        try:
            yield from stream_zip(images())
        finally:
            release_memory()

    safe_key = re.sub(r"[^A-Za-z0-9_-]", "", folder_key)[:24] or "indirme"
    return StreamingResponse(
        generate(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="momenz-{safe_key}.zip"',
            "Cache-Control": "no-store",
            # Proxy'ler gövdeyi tamponlamasın; aksi halde uzun indirmede
            # kesilen akış kullanıcıya "corrupted zip" olarak görünüyor.
            "X-Accel-Buffering": "no",
        },
    )
