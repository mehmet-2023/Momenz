from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from ..db import D1Client
from ..deps import get_db, require_user
from ..schemas import FolderCreateIn, FolderListOut, FolderOut, MessageOut
from ..services import folders as service

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("", response_model=FolderListOut)
def list_folders(
    include_hidden: bool = Query(default=False),
    db: D1Client = Depends(get_db),
    user=Depends(require_user),
) -> FolderListOut:
    return service.list_folders(db, user.id, include_hidden)


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(
    payload: FolderCreateIn,
    response: Response,
    db: D1Client = Depends(get_db),
    user=Depends(require_user),
) -> FolderOut:
    folder, job_id = service.create_folder(db, user.id, payload)
    response.headers["Location"] = f"/api/v1/jobs/{job_id}"
    response.headers["X-Job-ID"] = job_id
    return folder


@router.get("/{folder_key}", response_model=FolderOut)
def get_folder(
    folder_key: str,
    db: D1Client = Depends(get_db),
    user=Depends(require_user),
) -> FolderOut:
    return service.get_folder(db, user.id, folder_key)


@router.delete("/{folder_key}", response_model=MessageOut)
def delete_folder(
    folder_key: str,
    db: D1Client = Depends(get_db),
    user=Depends(require_user),
) -> MessageOut:
    if not service.delete_folder(db, user.id, folder_key):
        from ..errors import NotFound

        raise NotFound("Klasör bulunamadı.")
    return MessageOut(message="Klasör ve indeksi silindi.")
