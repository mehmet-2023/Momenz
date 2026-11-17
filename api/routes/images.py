from __future__ import annotations

import hashlib
import io
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse

from core.image_utils import encode_jpeg_bytes

from ..config import Settings, get_settings
from ..db import D1Client
from ..deps import get_db, require_user
from ..errors import Forbidden, NotFound
from ..repositories import folders as folder_repo
from ..repositories import index as index_repo
from ..schemas import PreviewZipIn

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
    size: int = Query(default=384, ge=64, le=1024),
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user=Depends(require_user),
) -> Response:
    _assert_file_access(db, user.id, folder_key, file_id)

    path = _thumb_path(settings, file_id, size)
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

    def generate():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
            for file_id in ids:
                try:
                    image = client.fetch_image(file_id, settings.preview_thumb_size)
                    if image is None:
                        continue
                    archive.writestr(
                        f"{file_id}.jpg", encode_jpeg_bytes(image, quality=80)
                    )
                except Exception:
                    continue
        yield buffer.getvalue()

    return StreamingResponse(
        generate(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="momenz-eslesenler.zip"'
        },
    )
