from __future__ import annotations

import re
import threading
from typing import Any, Iterable

from api.db import TursoClient, TursoError

from .d1_store import D1Store, D1Error
from .store_base import StoreError


class TursoStore(D1Store):
    """D1Store ile aynı public arayüzü Turso/libSQL üzerinde sunar.

    D1Store'un SQL ve şema mantığı yeniden kullanılır; yalnızca taşıma katmanı
    (``_query`` / ``_batch``) Turso istemcisine yönlendirilir.
    """

    def __init__(
        self,
        config: dict[str, Any],
        table: str = "drive_face_index",
        *,
        timeout: tuple[float, float] | None = None,
        max_retries: int = 4,
        batch_size: int = 100,
        page_size: int = 4000,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError("Geçersiz tablo adı.")

        database_url = str(config.get("database_url") or "").strip()
        auth_token = str(config.get("auth_token") or "").strip()
        if not (database_url and auth_token):
            raise D1Error(
                "Turso ayarları eksik (database_url, auth_token)."
            )

        self.table = table
        self.database_url = database_url
        self.timeout = timeout or config.get("timeout")
        self.max_retries = int(config.get("max_retries", max_retries))
        self.batch_size = max(1, int(batch_size))
        self.page_size = max(1, int(page_size))
        self._schema_ready = False
        self._schema_lock = threading.Lock()
        self._db = TursoClient(
            database_url,
            auth_token,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.database_url)

    def cache_identity(self) -> str:
        return f"turso:{self.database_url}"

    # ------------------------------------------------------------- transport

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            statements = [
                part.strip()
                for part in self._SCHEMA_SQL.split(";")
                if part.strip()
            ]
            self._batch([{"sql": statement} for statement in statements])
            self._schema_ready = True

    _SCHEMA_SQL = """
        CREATE TABLE IF NOT EXISTS drive_face_index (
            folder_key TEXT NOT NULL,
            file_id TEXT NOT NULL,
            name TEXT,
            path TEXT,
            width INTEGER NOT NULL DEFAULT 0,
            height INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'done',
            error TEXT,
            faces TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            claimed_at TEXT,
            PRIMARY KEY (folder_key, file_id)
        );
        CREATE INDEX IF NOT EXISTS drive_face_index_folder_key_idx
        ON drive_face_index (folder_key);
        CREATE INDEX IF NOT EXISTS drive_face_index_file_id_idx
        ON drive_face_index (file_id);
        CREATE TABLE IF NOT EXISTS drive_folders (
            folder_key TEXT PRIMARY KEY,
            meta TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS drive_indexed_folders (
            folder_id TEXT PRIMARY KEY,
            root_key TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS drive_indexed_folders_root_idx
        ON drive_indexed_folders (root_key);
        """

    def _query(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> list[dict[str, Any]]:
        return self._db.query(sql, params)

    def _batch(self, statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not statements:
            return []
        output: list[dict[str, Any]] = []
        for start in range(0, len(statements), self.batch_size):
            chunk = statements[start : start + self.batch_size]
            result = self._db.batch(chunk)
            for item in result:
                if not item.get("success", True):
                    raise D1Error(str(item.get("error") or "Turso batch başarısız."))
            output.extend(result)
        return output

    def close(self) -> None:
        self._db.close()


__all__ = ["TursoStore", "TursoError", "StoreError"]
