from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..db import D1Client
from ..deps import get_db, require_user
from ..schemas import JobListOut, JobOut, MessageOut
from ..services import jobs as service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListOut)
def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    folder_key: str | None = Query(default=None),
    db: D1Client = Depends(get_db),
    user=Depends(require_user),
) -> JobListOut:
    return service.list_jobs(db, user.id, limit, folder_key)


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    db: D1Client = Depends(get_db),
    user=Depends(require_user),
) -> JobOut:
    return service.get_job(db, user.id, job_id)


@router.post("/{job_id}/cancel", response_model=MessageOut)
def cancel_job(
    job_id: str,
    db: D1Client = Depends(get_db),
    user=Depends(require_user),
) -> MessageOut:
    if not service.cancel_job(db, user.id, job_id):
        from ..errors import NotFound

        raise NotFound("İş bulunamadı veya zaten bitmiş.")
    return MessageOut(message="İş iptal edildi.")
