from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from api.db import TursoClient
from api.repositories import index as index_repo


class OneRowStore:
    """Klasörün tam face index'ini tek Turso satırında tutan store.

    ``PgIndexStore``'un beklediği arayüzü sağlar; tüm okumalar ``folder_matrices``
    satırının bir kez yüklenmesinden, tüm yazmalar bellekteki sözlüğe gider.
    ``persist()`` çağrıldığinde klasörün tamamı TEK SQL yazımıyla kaydedilir.
    Böylece klasör başına 20 bin satır okuma/yazma yerine 1 okuma + 1 yazma
    olur.
    """

    def __init__(self, db: TursoClient, folder_key: str) -> None:
        self.db = db
        self.folder_key = str(folder_key)
        self._version = 0
        self._files: dict[str, dict] = {}
        self._meta: dict[str, Any] = {}
        self._loaded = False

    def cache_identity(self) -> str:
        return f"one-row:{self.folder_key}"

    # ------------------------------------------------------------- tek okuma

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        loaded = index_repo.load_index_row(self.db, self.folder_key)
        if loaded is not None:
            version, files, meta = loaded
            self._version = int(version)
            self._files = {
                str(row.get("file_id") or ""): row
                for row in files
                if str(row.get("file_id") or "")
            }
            self._meta = meta
        self._loaded = True

    def version(self) -> int:
        self._ensure_loaded()
        return int(self._version)

    # ---------------------------------------------------------------- okumalar

    def fetch(self, folder_key: str) -> list[dict]:
        self._ensure_loaded()
        return [dict(row) for row in self._files.values()]

    def fetch_existing(self, file_ids: list[str]) -> list[dict]:
        self._ensure_loaded()
        return [
            dict(self._files[file_id])
            for file_id in file_ids
            if file_id in self._files
            and str(self._files[file_id].get("status") or "") in ("done", "no_face")
        ]

    def count(self, folder_key: str) -> int:
        self._ensure_loaded()
        return len(self._files)

    def done_ids(self, folder_key: str) -> set[str]:
        self._ensure_loaded()
        return {
            file_id
            for file_id, row in self._files.items()
            if str(row.get("status") or "") in ("done", "no_face")
        }

    def has_image(self, folder_key: str, file_id: str) -> bool:
        self._ensure_loaded()
        return str(file_id) in self._files

    def sample_image(self, folder_key: str) -> tuple[str, str] | None:
        self._ensure_loaded()
        for file_id, row in self._files.items():
            path = str(row.get("path") or "")
            if path:
                return file_id, path
        return None

    def folder_stats(self, folder_key: str) -> dict[str, int]:
        self._ensure_loaded()
        counts = {"images": len(self._files), "done": 0, "no_face": 0, "errors": 0}
        faces = 0
        for row in self._files.values():
            status = str(row.get("status") or "")
            if status == "done":
                counts["done"] += 1
                faces += len(row.get("faces") or [])
            elif status == "no_face":
                counts["no_face"] += 1
            elif status == "error":
                counts["errors"] += 1
        counts["faces"] = faces
        return counts

    # --------------------------------------------------------------- meta okuma

    def get_folder_meta(
        self, folder_key: str, key: str, default: str | None = None
    ) -> str | None:
        self._ensure_loaded()
        value = self._meta.get(key, default)
        return None if value is None else str(value)

    def get_folder_meta_dict(self, folder_key: str) -> dict[str, Any]:
        self._ensure_loaded()
        return dict(self._meta)

    # ---------------------------------------------------------------- yazmalar

    def upsert(self, folder_key: str, rows: list[dict]) -> int:
        self._ensure_loaded()
        written = 0
        for row in rows:
            file_id = str(row.get("file_id") or "")
            if not file_id:
                continue
            self._files[file_id] = dict(row)
            written += 1
        return written

    def claim_images(
        self,
        folder_key: str,
        file_ids: list[str],
        *,
        force: bool = False,
        stale_minutes: int = 30,
    ) -> set[str]:
        self._ensure_loaded()
        now = datetime.now(timezone.utc)
        stale_limit = now - timedelta(minutes=max(1, int(stale_minutes)))
        claimed: set[str] = set()
        for raw_id in file_ids:
            file_id = str(raw_id)
            if not file_id:
                continue
            row = self._files.get(file_id)
            if row is None:
                row = {
                    "file_id": file_id,
                    "name": "",
                    "path": "",
                    "width": 0,
                    "height": 0,
                    "status": "processing",
                    "error": None,
                    "faces": [],
                }
                self._files[file_id] = row
            status = str(row.get("status") or "")
            if status in ("done", "no_face") and not force:
                continue
            claimed_at = str(row.get("claimed_at") or "")
            if claimed_at and not force:
                try:
                    parsed = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    if parsed > stale_limit:
                        continue
                except ValueError:
                    pass
            row["status"] = "processing"
            row["claimed_at"] = now.isoformat(timespec="seconds")
            claimed.add(file_id)
        return claimed

    def set_folder_meta(self, folder_key: str, key: str, value: str) -> None:
        self._ensure_loaded()
        self._meta[str(key)] = str(value)

    def set_folder_meta_dict(self, folder_key: str, meta: dict[str, Any]) -> None:
        self._ensure_loaded()
        self._meta = dict(meta or {})

    def delete_folder(self, folder_key: str) -> int:
        self._files.clear()
        self._meta.clear()
        self._loaded = True
        return 0

    # ------------------------------------------------------------- tek yazma

    def persist(self, version: int | None = None) -> int:
        """Bellekteki tam index'i TEK SQL satırı olarak yazar."""
        self._ensure_loaded()
        next_version = int(version) if version is not None else self._version + 1
        index_repo.save_index_row(
            self.db,
            self.folder_key,
            next_version,
            list(self._files.values()),
            self._meta,
        )
        self._version = next_version
        return next_version


__all__ = ["OneRowStore"]
