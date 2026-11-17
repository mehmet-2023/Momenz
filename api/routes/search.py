from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from core.config import DEFAULT_DET_THRESHOLD, DEFAULT_MIN_FACE
from core.image_utils import decode_image_bytes

from ..config import Settings, get_settings
from ..db import D1Client
from ..deps import get_db, require_user
from ..errors import Forbidden, UpstreamError
from ..repositories import folders as folder_repo
from ..schemas import SearchOut, SearchResultOut
from ..services.search import SearchService

router = APIRouter(prefix="/search", tags=["search"])


def _search_service(request: Request) -> SearchService:
    service = getattr(request.app.state, "search", None)
    if service is None:
        raise RuntimeError("SearchService başlatılmadı.")
    return service


@router.post("", response_model=SearchOut)
async def search(
    request: Request,
    folder_key: str = Form(...),
    file: UploadFile = File(...),
    threshold: float | None = Form(default=None),
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user=Depends(require_user),
) -> SearchOut:
    if not folder_repo.exists_for_user(db, user.id, folder_key):
        raise Forbidden("Bu klasöre erişim iznin yok.")

    data = await file.read()
    if not data or len(data) > 12 * 1024 * 1024:
        from ..errors import AppError

        raise AppError("Fotoğraf boş veya çok büyük (en fazla 12 MB).")

    image = decode_image_bytes(data)
    if image is None:
        from ..errors import AppError

        raise AppError("Fotoğraf açılamadı. JPG, PNG veya WebP dene.")

    engine = getattr(request.app.state, "face_engine", None)
    if engine is None:
        raise UpstreamError("Yüz tanıma modeli hazır değil.")

    faces, _ = engine.analyze(
        image,
        det_threshold=DEFAULT_DET_THRESHOLD,
        min_face=DEFAULT_MIN_FACE,
        max_faces=10,
        input_max_side=1280,
    )
    if not faces:
        return SearchOut(folder_key=folder_key, count=0, results=[], took_ms=0.0)

    probe = np.asarray(faces[0]["embedding"], dtype=np.float32).reshape(-1)
    results, took_ms = _search_service(request).search(
        db,
        folder_key,
        probe,
        threshold=threshold,
    )

    items = []
    for result in results:
        file_id = str(result.get("file_id") or "")
        url_kwargs = {"folder_key": folder_key}
        items.append(
            SearchResultOut(
                file_id=file_id,
                name=str(result.get("name") or ""),
                path=result.get("path"),
                score=float(result.get("score") or 0.0),
                width=int(result.get("width") or 0),
                height=int(result.get("height") or 0),
                thumb_url=f"/api/v1/images/{file_id}/thumb?folder_key={folder_key}",
                download_url=f"/api/v1/images/{file_id}/download?folder_key={folder_key}",
                drive_url=f"https://drive.google.com/file/d/{file_id}/view",
            )
        )
    return SearchOut(
        folder_key=folder_key, count=len(items), results=items, took_ms=round(took_ms, 2)
    )
