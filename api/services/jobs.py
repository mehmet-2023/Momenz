from __future__ import annotations

from typing import Any

from ..db import D1Client
from ..errors import NotFound
from ..repositories import jobs as repo
from ..schemas import JobListOut, JobOut
from ..security import new_id


def enqueue(
    db: D1Client,
    owner_id: str,
    folder_key: str,
    *,
    kind: str = "index",
    payload: dict[str, Any] | None = None,
) -> JobOut:
    job = repo.create(
        db,
        job_id=new_id(),
        owner_id=owner_id,
        folder_key=folder_key,
        kind=kind,
        payload=payload,
    )
    return JobOut(**job)


def get_job(db: D1Client, owner_id: str, job_id: str) -> JobOut:
    job = repo.get_for_user(db, owner_id, job_id)
    if not job:
        raise NotFound("İş bulunamadı.")
    return JobOut(**job)


def list_jobs(
    db: D1Client, owner_id: str, limit: int = 50, folder_key: str | None = None
) -> JobListOut:
    items = repo.list_for_user(db, owner_id, limit, folder_key)
    return JobListOut(items=[JobOut(**item) for item in items], total=len(items))


def cancel_job(db: D1Client, owner_id: str, job_id: str) -> bool:
    return repo.cancel(db, owner_id, job_id)
