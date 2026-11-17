from __future__ import annotations

from datetime import datetime, timezone

from core.config import DEFAULT_THUMB_SIZE, folder_key as make_folder_key
from core.drive import parse_drive_folder_url

from ..db import D1Client
from ..errors import NotFound, UpstreamError
from ..repositories import folders as repo
from ..schemas import FolderCreateIn, FolderListOut, FolderOut
from . import jobs as job_service
from .drive import get_drive_client


def _meta(meta: dict) -> dict:
    date = meta.get("folder_date") or meta.get("added_at") or ""
    label = ""
    if date:
        text = str(date).strip().replace("Z", "+00:00")
        try:
            label = datetime.fromisoformat(text).astimezone(timezone.utc).strftime(
                "%d.%m.%Y"
            )
        except ValueError:
            label = str(date)[:10]
    return {
        "key": str(meta.get("folder_key") or ""),
        "title": str(meta.get("folder_title") or meta.get("folder_url") or "Klasör"),
        "folder_id": meta.get("folder_id"),
        "url": meta.get("folder_url"),
        "image_count": int(meta.get("image_count") or 0),
        "face_count": int(meta.get("face_count") or 0),
        "hidden": str(meta.get("folder_hidden") or "0") == "1",
        "date_label": label or None,
        "created_at": meta.get("updated_at"),
    }


def list_folders(db: D1Client, owner_id: str, include_hidden: bool = False) -> FolderListOut:
    rows = repo.list_for_user(db, owner_id)
    items = []
    for row in rows:
        meta = row["meta"]
        if not include_hidden and str(meta.get("folder_hidden") or "0") == "1":
            continue
        items.append(FolderOut(**_meta({**row, **meta})))
    return FolderListOut(items=items, total=len(items))


def get_folder(db: D1Client, owner_id: str, key: str) -> FolderOut:
    row = repo.get_for_user(db, owner_id, key)
    if not row:
        raise NotFound("Klasör bulunamadı.")
    meta = loads_meta(row)
    return FolderOut(**_meta({**row, **meta, "image_count": row.get("image_count", 0)}))


def loads_meta(row: dict) -> dict:
    value = row.get("meta")
    if isinstance(value, dict):
        return value
    import json

    try:
        return json.loads(str(value or "{}"))
    except ValueError:
        return {}


def create_folder(
    db: D1Client, owner_id: str, payload: FolderCreateIn
) -> tuple[FolderOut, str]:
    """Klasörü kaydeder ve index job'u oluşturur. (FolderOut, job_id) döner."""
    try:
        folder_id, resource_key = parse_drive_folder_url(payload.url.strip())
    except Exception as exc:
        raise UpstreamError(f"Drive klasör linki okunamadı: {exc}") from exc

    key = make_folder_key(
        folder_id, resource_key, payload.include_subfolders, DEFAULT_THUMB_SIZE
    )
    meta: dict = {
        "folder_url": payload.url.strip(),
        "folder_id": folder_id,
        "folder_hidden": "1" if payload.hidden else "0",
        "include_subfolders": "1" if payload.include_subfolders else "0",
        "thumb_size": str(DEFAULT_THUMB_SIZE),
        "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    drive_meta: dict = {}
    try:
        drive_meta = get_drive_client().get_folder_meta(folder_id) or {}
    except Exception:
        # Meta okunamazsa job yine de çalışır; başlık sonradan doldurulur.
        pass
    if drive_meta.get("name"):
        meta["folder_title"] = drive_meta["name"]
    drive_date = drive_meta.get("created_time") or drive_meta.get("modified_time")
    if drive_date:
        meta["folder_date"] = drive_date

    repo.upsert(db, owner_id, key, meta)
    job = job_service.enqueue(
        db,
        owner_id,
        key,
        payload={"folder_id": folder_id, "resource_key": resource_key},
    )
    return get_folder(db, owner_id, key), job.id


def delete_folder(db: D1Client, owner_id: str, key: str) -> bool:
    return repo.delete(db, owner_id, key)
