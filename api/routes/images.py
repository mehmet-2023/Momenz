from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse

from core.image_utils import encode_jpeg_bytes
from core.mem import release_memory
from core.zip_stream import stream_zip

from ..config import Settings, get_settings
from ..db import D1Client
from ..deps import get_db, require_user
from ..errors import Forbidden, NotFound
from ..repositories import folders as folder_repo
from ..repositories import index as index_repo
from ..schemas import PreviewZipIn
from ..services.thumbnails import render_thumbnail

router = APIRouter(prefix="/images", tags=["images"])


def _assert_file_access(
    db: D1Client, user_id: str, folder_key: str, file_id: str
) -> None:
    if not folder_repo.exists_for_user(db, user_id, folder_key):
        raise Forbidden("Bu klasöre erişim iznin yok.")
    if not index_repo.file_ids(db, folder_key, [file_id]):
        raise NotFound("Fotoğraf bu klasörde bulunamadı.")


def _thumb_path(settings: Settings, file_id: str, size: int) -> Path:
    digest = hashlib.sha1(f"{file_id}:{size}".encode("utf-8")).hexdigest()
    return Path(settings.thumb_cache_dir) / f"{digest[:2]}" / f"{digest}.jpg"


@router.get("/{file_id}/thumb")
def thumbnail(
    file_id: str,
    folder_key: str = Query(...),
    size: int = Query(default=320, ge=64, le=2048),
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user=Depends(require_user),
) -> Response:
    _assert_file_access(db, user.id, folder_key, file_id)
    size = min(size, 512)

    path = _thumb_path(settings, file_id, size)
    data = render_thumbnail(settings, file_id, size, path)
    if data is None:
        raise NotFound("Önizleme alınamadı.")
    return Response(
        data,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800"},
    )


@router.get("/{file_id}/download")
def download(
    file_id: str,
    folder_key: str = Query(...),
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user=Depends(require_user),
) -> Response:
    _assert_file_access(db, user.id, folder_key, file_id)
    from ..services.drive import get_drive_client

    result = get_drive_client(settings).fetch_file_bytes(file_id)
    if not result:
        raise NotFound("Dosya indirilemedi.")
    data, mime = result
    safe_name = file_id.replace("/", "_").replace("\\", "_")[:120]
    return Response(
        data,
        media_type=mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.post("/preview.zip")
def preview_zip(
    payload: PreviewZipIn,
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user=Depends(require_user),
) -> StreamingResponse:
    if not folder_repo.exists_for_user(db, user.id, payload.folder_key):
        raise Forbidden("Bu klasöre erişim iznin yok.")
    ids = index_repo.file_ids(db, payload.folder_key, payload.file_ids)
    if not ids:
        raise NotFound("İndirilecek fotoğraf bulunamadı.")

    from ..services.drive import get_drive_client

    client = get_drive_client(settings)

    def images():
        for file_id in ids:
            try:
                image = client.fetch_image(file_id, settings.preview_thumb_size)
                if image is None:
                    continue
                yield f"{file_id}.jpg", encode_jpeg_bytes(image, quality=80)
            except Exception:
                continue

    def generate():
        try:
            yield from stream_zip(images())
        finally:
            release_memory()

    return StreamingResponse(
        generate(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="momenz-eslesenler.zip"'
        },
    )
