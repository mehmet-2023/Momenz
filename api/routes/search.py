from __future__ import annotations

import json
import threading

import numpy as np
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from core.config import EMBEDDING_SIZE
from core.image_utils import decode_image_bytes
from core.mem import release_memory

from ..config import Settings, get_settings
from ..db import D1Client
from ..deps import get_db, optional_user
from ..errors import AppError, Forbidden, UpstreamError
from ..repositories import folders as folder_repo
from ..repositories import index as index_repo
from ..schemas import EmbedOut, SearchOut, SearchResultOut
from ..services.face import probe_embedding
from ..services.search import SearchService

router = APIRouter(prefix="/search", tags=["search"])

# 512 MB sınırında aynı anda birden fazla ağır iş matris/vektör üretirse OOM
# olur. Tek semaphore hem embed hem search yolunu serileştirir: yüz motoru
# tek örnek, matris de klasör başına tek kopya.
_heavy_lock = threading.BoundedSemaphore(1)


def _search_service(request: Request) -> SearchService:
    service = getattr(request.app.state, "search", None)
    if service is None:
        raise RuntimeError("SearchService başlatılmadı.")
    return service


def _decode(data: bytes) -> np.ndarray:
    image = decode_image_bytes(data, max_side=768)
    if image is None:
        raise AppError("Fotoğraf açılamadı. JPG, PNG veya WebP dene.")
    return image


def _read_upload(file: UploadFile) -> bytes:
    data = file.file.read()
    if not data or len(data) > 12 * 1024 * 1024:
        raise AppError("Fotoğraf boş veya çok büyük (en fazla 12 MB).")
    return data


def _parse_embedding(raw: str | None) -> np.ndarray | None:
    """İstemci tarayıcıda hesaplanmış vektörü doğrular.

    Geçersiz/eksik vektör yollanırsa None döner ve sunucu görselden yeniden
    hesaplar. Kötü vektör yalnızca isteyen kullanıcının sonuçlarını etkiler;
    D1 verisi açığa çıkmaz.
    """
    if not raw:
        return None
    try:
        values = json.loads(raw)
        if not isinstance(values, list) or len(values) != EMBEDDING_SIZE:
            return None
        vector = np.asarray(values, dtype=np.float32)
        if not np.all(np.isfinite(vector)) or not np.any(vector):
            return None
        return vector
    except (ValueError, TypeError, OverflowError):
        return None


def _embed(data: bytes) -> np.ndarray:
    """Görselden yüz vektörü üretir; D1'e hiç dokunmaz."""
    with _heavy_lock:
        try:
            probe = probe_embedding(_decode(data))
        except AppError:
            raise
        except Exception as exc:
            raise UpstreamError(f"Yüz tanıma modeli hazır değil: {exc}") from exc
        finally:
            release_memory()
    return probe


def _search(
    probe: np.ndarray,
    service: SearchService,
    db: D1Client,
    folder_key: str,
    threshold: float | None,
    version: int,
) -> tuple[list[dict], float]:
    if probe.size == 0:
        return [], 0.0
    with _heavy_lock:
        try:
            return service.search(
                db,
                folder_key,
                probe,
                threshold=threshold,
                version=version,
            )
        finally:
            release_memory()


@router.post("/embed", response_model=EmbedOut)
async def embed(file: UploadFile = File(...)) -> EmbedOut:
    """Yalnızca yüz vektörü döner — D1 okuma/yazma yok, matrix kurulmaz.

    Tarayıcı bu vektörü IndexedDB'de saklar ve bir sonraki yüzde benzerlik
    karşılaştırması yapar. %70-80 eşik üstü eşleşmede /search hiç çağrılmaz,
    dolayısıyla D1'e hiç gidilmez.
    """
    data = await run_in_threadpool(_read_upload, file)
    probe = await run_in_threadpool(_embed, data)
    del data
    if probe.size != EMBEDDING_SIZE:
        return EmbedOut(embedding=[], ok=False)
    return EmbedOut(embedding=[float(v) for v in probe], ok=True)


@router.post("", response_model=SearchOut)
async def search(
    request: Request,
    folder_key: str = Form(...),
    file: UploadFile | None = File(default=None),
    embedding: str | None = Form(default=None),
    threshold: float | None = Form(default=None),
    db: D1Client = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user=Depends(optional_user),
) -> SearchOut:
    # Tek D1 isteği: yayın durumu + index versiyonu birlikte okunur.
    is_public, version = index_repo.public_and_version(db, folder_key)
    if not is_public and (
        not user or not folder_repo.exists_for_user(db, user.id, folder_key)
    ):
        raise Forbidden("Bu klasöre erişim iznin yok.")

    # Tarayıcı benzerlik kontrolü için vektörü zaten hesaplattıysa görseli
    # yeniden yüklemeye ve yüzü ikinci kez analiz etmeye gerek yok.
    probe = _parse_embedding(embedding)
    if probe is None:
        if file is None:
            raise AppError("Fotoğraf veya embedding gerekli.")
        data = await run_in_threadpool(_read_upload, file)
        probe = await run_in_threadpool(_embed, data)
        del data

    results, took_ms = await run_in_threadpool(
        _search,
        probe,
        _search_service(request),
        db,
        folder_key,
        threshold,
        version,
    )

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
        folder_key=folder_key,
        count=len(items),
        results=items,
        took_ms=round(took_ms, 2),
        query_embedding=[float(v) for v in probe],
    )
