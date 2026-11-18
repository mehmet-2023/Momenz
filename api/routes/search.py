from __future__ import annotations

import threading

import numpy as np
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from core.config import DEFAULT_DET_THRESHOLD, DEFAULT_MIN_FACE
from core.image_utils import decode_image_bytes
from core.mem import release_memory

from ..config import Settings, get_settings
from ..db import D1Client
from ..deps import get_db, optional_user
from ..errors import Forbidden, UpstreamError
from ..repositories import events as event_repo
from ..repositories import folders as folder_repo
from ..schemas import SearchOut, SearchResultOut
from ..services.face import get_face_engine
from ..services.search import SearchService

router = APIRouter(prefix="/search", tags=["search"])

# 512 MB sınırında aynı anda birden fazla ağır arama matris kurarsa OOM olur.
# CPU işi threadpool'da çalışır; semaphore yalnızca birinin matris üretmesine izin verir.
_heavy_lock = threading.BoundedSemaphore(1)


def _search_service(request: Request) -> SearchService:
    service = getattr(request.app.state, "search", None)
    if service is None:
        raise RuntimeError("SearchService başlatılmadı.")
    return service


def _heavy_search(
    image: np.ndarray,
    service: SearchService,
    db: D1Client,
    folder_key: str,
    threshold: float | None,
) -> tuple[list[dict], float]:
    with _heavy_lock:
        try:
            engine = get_face_engine()
        except Exception as exc:
            raise UpstreamError(f"Yüz tanıma modeli hazır değil: {exc}") from exc

        faces, _ = engine.analyze(
            image,
            det_threshold=DEFAULT_DET_THRESHOLD,
            min_face=DEFAULT_MIN_FACE,
            max_faces=5,
            input_max_side=768,
        )
        if not faces:
            return [], 0.0

        probe = np.asarray(faces[0]["embedding"], dtype=np.float32).reshape(-1)
        try:
            return service.search(db, folder_key, probe, threshold=threshold)
        finally:
            release_memory()


@router.post("", response_model=SearchOut)
async def search(
    request: Request,
    folder_key: str = Form(...),
    file: UploadFile = File(...),
    threshold: float | None = Form(default=None),
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user=Depends(optional_user),
) -> SearchOut:
    is_public = event_repo.is_public_folder(db, folder_key)
    if not is_public and (
        not user or not folder_repo.exists_for_user(db, user.id, folder_key)
    ):
        raise Forbidden("Bu klasöre erişim iznin yok.")

    data = await file.read()
    if not data or len(data) > 12 * 1024 * 1024:
        from ..errors import AppError

        raise AppError("Fotoğraf boş veya çok büyük (en fazla 12 MB).")

    # JPEG'i gereken çözünürlükte decode et; 12 MB ham dosyayı RAM'e açmayız.
    image = decode_image_bytes(data, max_side=768)
    del data
    if image is None:
        from ..errors import AppError

        raise AppError("Fotoğraf açılamadı. JPG, PNG veya WebP dene.")

    results, took_ms = await run_in_threadpool(
        _heavy_search,
        image,
        _search_service(request),
        db,
        folder_key,
        threshold,
    )
    del image

    items: list[SearchResultOut] = []
    for result in results:
        file_id = str(result.get("file_id") or "")
        items.append(
            SearchResultOut(
                file_id=file_id,
                name=str(result.get("name") or ""),
                path=result.get("path"),
                score=float(result.get("score") or 0.0),
                width=int(result.get("width") or 0),
                height=int(result.get("height") or 0),
                thumb_url=(
                    f"/api/v1/public/folders/{folder_key}/photos/{file_id}/thumb?size=320"
                    if is_public
                    else f"/api/v1/images/{file_id}/thumb?folder_key={folder_key}"
                ),
                download_url=(
                    None
                    if is_public
                    else f"/api/v1/images/{file_id}/download?folder_key={folder_key}"
                ),
                drive_url=f"https://drive.google.com/file/d/{file_id}/view",
                drive_download_url=(
                    f"https://drive.google.com/uc?export=download&id={file_id}"
                ),
            )
        )
    return SearchOut(
        folder_key=folder_key, count=len(items), results=items, took_ms=round(took_ms, 2)
    )
