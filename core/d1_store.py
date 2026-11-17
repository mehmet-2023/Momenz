from __future__ import annotations

import json
import random
import re
import threading
import time
from typing import Any, Iterable

import requests

from .store_base import StoreError

# Cloudflare D1 REST API'nin belgelenmiş sınırları:
# - sorgu başına en fazla 100 bound parameter
# - SQL ifadesi başına en fazla 100 KB
# - sorgu sonucu en fazla 50 MB
_MAX_BOUND_PARAMS = 100
_DEFAULT_PAGE_SIZE = 4000
_DEFAULT_BATCH_SIZE = 100


class D1Error(StoreError):
    """Cloudflare D1 bağlantı ve sorgu hataları."""


class D1Store:
    """Cloudflare D1 üzerinde kalıcı indeks saklar.

    ``create_store()`` arayüzüyle aynı yöntemleri sunar. Bağlantı yoktur;
    her sorgu Cloudflare D1 REST API'sine HTTP isteği olarak gider ve
    ``batch`` kullanılarak toplu yazımlar tek istekte yapılır.

    Gerekli ayarlar::

        account_id  : Cloudflare hesap kimliği
        database_id : D1 veritabanı kimliği (UUID)
        api_token   : D1 Edit yetkili API token'ı
    """

    def __init__(
        self,
        config: dict[str, Any],
        table: str = "drive_face_index",
        *,
        timeout: tuple[float, float] = (10.0, 90.0),
        max_retries: int = 4,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError("Geçersiz tablo adı.")

        self.table = table
        self.account_id = str(config.get("account_id") or "").strip()
        self.database_id = str(config.get("database_id") or "").strip()
        self.api_token = str(
            config.get("api_token") or config.get("token") or ""
        ).strip()
        if not (self.account_id and self.database_id and self.api_token):
            raise D1Error(
                "D1 ayarları eksik (account_id, database_id, api_token)."
            )

        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.batch_size = max(1, int(batch_size))
        self.page_size = max(1, int(page_size))
        self._schema_ready = False
        self._schema_lock = threading.Lock()
        self._local = threading.local()
        self._url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/d1/database/{self.database_id}/query"
        )

    @property
    def enabled(self) -> bool:
        return bool(self.account_id and self.database_id and self.api_token)

    def cache_identity(self) -> str:
        return f"d1:{self.database_id}"

    # ------------------------------------------------------------- transport

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
            )
            self._local.session = session
        return session

    def _post(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """REST çağrısını yapar; geçici hatalarda üstel backoff ile dener."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            retryable = False
            try:
                response = self._session().post(
                    self._url,
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                retryable = True
            else:
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = D1Error(
                        f"D1 HTTP {response.status_code}: {response.text[:300]}"
                    )
                    retryable = True
                else:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise D1Error(
                            f"D1 geçersiz yanıt döndü (HTTP {response.status_code})."
                        ) from exc

                    if data.get("success") is not True:
                        errors = data.get("errors") or []
                        detail = "; ".join(
                            str(item.get("message") or item)
                            if isinstance(item, dict)
                            else str(item)
                            for item in errors
                        )
                        raise D1Error(
                            detail
                            or f"D1 isteği başarısız (HTTP {response.status_code})."
                        )

                    return list(data.get("result") or [])

            if not retryable or attempt >= self.max_retries:
                break
            delay = min(8.0, 0.5 * (2**attempt)) + random.random() * 0.25
            time.sleep(delay)

        if isinstance(last_error, D1Error):
            raise last_error
        raise D1Error(str(last_error) or "D1 isteği başarısız.")

    def _query(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"sql": sql}
        if params is not None:
            payload["params"] = list(params)
        result = self._post(payload)
        if not result:
            return []
        first = result[0]
        if not first.get("success", True):
            raise D1Error(str(first.get("error") or "D1 sorgusu başarısız."))
        return list(first.get("results") or [])

    def _batch(
        self, statements: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Birden fazla ifadeyi D1 ``batch`` endpoint'i ile çalıştırır."""
        if not statements:
            return []

        output: list[dict[str, Any]] = []
        for start in range(0, len(statements), self.batch_size):
            chunk = statements[start : start + self.batch_size]
            result = self._post({"batch": chunk})
            for item in result:
                if not item.get("success", True):
                    raise D1Error(
                        str(item.get("error") or "D1 batch ifadesi başarısız.")
                    )
            output.extend(result)
        return output

    # ---------------------------------------------------------------- schema

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return

            self._query(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
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
                CREATE INDEX IF NOT EXISTS {self.table}_folder_key_idx
                ON {self.table} (folder_key);
                CREATE INDEX IF NOT EXISTS {self.table}_file_id_idx
                ON {self.table} (file_id);
                CREATE TABLE IF NOT EXISTS drive_folders (
                    folder_key TEXT PRIMARY KEY,
                    meta TEXT NOT NULL DEFAULT '{{}}',
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
            )
            self._schema_ready = True

    # ----------------------------------------------------------------- reads

    def ping(self) -> bool:
        self._ensure_schema()
        rows = self._query("SELECT 1 AS ok")
        return bool(rows and int(rows[0].get("ok") or 0) == 1)

    def count(self, folder_key: str) -> int:
        self._ensure_schema()
        rows = self._query(
            f"SELECT COUNT(*) AS total FROM {self.table} WHERE folder_key = ?",
            (folder_key,),
        )
        return int((rows[0] if rows else {}).get("total") or 0)

    def fetch(self, folder_key: str) -> list[dict]:
        """Klasördeki tüm satırları keyset pagination ile okur.

        D1'in 50 MB sorgu sonucu sınırına takılmamak için parça parça
        okunur; her parça 4000 satırdır.
        """
        self._ensure_schema()
        output: list[dict] = []
        last_id = ""

        while True:
            rows = self._query(
                f"""
                SELECT file_id, name, path, width, height, status, error, faces
                FROM {self.table}
                WHERE folder_key = ? AND file_id > ?
                ORDER BY file_id
                LIMIT ?
                """,
                (folder_key, last_id, self.page_size),
            )
            if not rows:
                break

            for row in rows:
                faces = row.get("faces")
                if isinstance(faces, str):
                    try:
                        faces = json.loads(faces)
                    except ValueError:
                        faces = []
                output.append(
                    {
                        "file_id": str(row.get("file_id") or ""),
                        "name": str(row.get("name") or ""),
                        "path": str(row.get("path") or ""),
                        "width": int(row.get("width") or 0),
                        "height": int(row.get("height") or 0),
                        "status": str(row.get("status") or "done"),
                        "error": row.get("error"),
                        "faces": faces or [],
                    }
                )

            last_id = str(rows[-1].get("file_id") or "")
            if len(rows) < self.page_size or not last_id:
                break

        return output

    def fetch_existing(self, file_ids: list[str]) -> list[dict]:
        if not file_ids:
            return []
        self._ensure_schema()

        # 100 bound parameter sınırı: 10 tanesi sorgu için ayrılır.
        chunk_size = _MAX_BOUND_PARAMS - 10
        found: dict[str, dict] = {}

        for start in range(0, len(file_ids), chunk_size):
            chunk = [str(item) for item in file_ids[start : start + chunk_size]]
            placeholders = ",".join("?" for _ in chunk)
            rows = self._query(
                f"""
                SELECT file_id, name, path, width, height, status, error, faces
                FROM {self.table}
                WHERE file_id IN ({placeholders})
                  AND status IN ('done', 'no_face')
                ORDER BY file_id, updated_at DESC
                """,
                chunk,
            )
            for row in rows:
                file_id = str(row.get("file_id") or "")
                if not file_id or file_id in found:
                    continue
                faces = row.get("faces")
                if isinstance(faces, str):
                    try:
                        faces = json.loads(faces)
                    except ValueError:
                        faces = []
                found[file_id] = {
                    "file_id": file_id,
                    "name": str(row.get("name") or ""),
                    "path": str(row.get("path") or ""),
                    "width": int(row.get("width") or 0),
                    "height": int(row.get("height") or 0),
                    "status": str(row.get("status") or "done"),
                    "error": row.get("error"),
                    "faces": faces or [],
                }

        return list(found.values())

    def done_ids(self, folder_key: str) -> set[str]:
        self._ensure_schema()
        rows = self._query(
            f"""
            SELECT file_id FROM {self.table}
            WHERE folder_key = ? AND status IN ('done', 'no_face')
            """,
            (folder_key,),
        )
        return {str(row.get("file_id")) for row in rows if row.get("file_id")}

    def has_image(self, folder_key: str, file_id: str) -> bool:
        self._ensure_schema()
        rows = self._query(
            f"""
            SELECT 1 AS found FROM {self.table}
            WHERE folder_key = ? AND file_id = ? LIMIT 1
            """,
            (folder_key, file_id),
        )
        return bool(rows)

    def sample_image(self, folder_key: str) -> tuple[str, str] | None:
        self._ensure_schema()
        rows = self._query(
            f"""
            SELECT file_id, path FROM {self.table}
            WHERE folder_key = ? AND path IS NOT NULL AND path <> ''
            ORDER BY LENGTH(path) ASC LIMIT 1
            """,
            (folder_key,),
        )
        if not rows:
            return None
        return str(rows[0].get("file_id") or ""), str(rows[0].get("path") or "")

    def folder_stats(self, folder_key: str) -> dict:
        self._ensure_schema()
        rows = self._query(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done,
                SUM(CASE WHEN status = 'no_face' THEN 1 ELSE 0 END) AS no_face,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors,
                COALESCE(SUM(json_array_length(faces)), 0) AS faces
            FROM {self.table}
            WHERE folder_key = ?
            """,
            (folder_key,),
        )
        row = rows[0] if rows else {}
        return {
            "images": int(row.get("total") or 0),
            "done": int(row.get("done") or 0),
            "no_face": int(row.get("no_face") or 0),
            "errors": int(row.get("errors") or 0),
            "faces": int(row.get("faces") or 0),
        }

    # ---------------------------------------------------------------- writes

    def upsert(self, folder_key: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        self._ensure_schema()

        statements: list[dict[str, Any]] = []
        for row in rows:
            file_id = str(row.get("file_id") or "")
            if not file_id:
                continue
            statements.append(
                {
                    "sql": f"""
                        INSERT INTO {self.table}
                            (folder_key, file_id, name, path, width, height,
                             status, error, faces, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT (folder_key, file_id) DO UPDATE SET
                            name = excluded.name,
                            path = excluded.path,
                            width = excluded.width,
                            height = excluded.height,
                            status = excluded.status,
                            error = excluded.error,
                            faces = excluded.faces,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                    "params": [
                        folder_key,
                        file_id,
                        str(row.get("name") or ""),
                        str(row.get("path") or ""),
                        int(row.get("width") or 0),
                        int(row.get("height") or 0),
                        str(row.get("status") or "done"),
                        row.get("error"),
                        json.dumps(row.get("faces") or [], ensure_ascii=False),
                    ],
                }
            )

        if not statements:
            return 0
        self._batch(statements)
        return len(statements)

    def delete_folder(self, folder_key: str) -> int:
        self._ensure_schema()
        self._query(
            f"DELETE FROM {self.table} WHERE folder_key = ?",
            (folder_key,),
        )
        return 0

    def claim_images(
        self,
        folder_key: str,
        file_ids: list[str],
        *,
        force: bool = False,
        stale_minutes: int = 30,
    ) -> set[str]:
        if not file_ids:
            return set()
        self._ensure_schema()

        force_value = 1 if force else 0
        stale = f"-{max(1, int(stale_minutes))} minutes"
        statements: list[dict[str, Any]] = []

        for raw_id in file_ids:
            file_id = str(raw_id)
            if not file_id:
                continue
            statements.append(
                {
                    "sql": f"""
                        INSERT INTO {self.table}
                            (folder_key, file_id, name, path, status,
                             updated_at, claimed_at)
                        VALUES (?, ?, '', '', 'processing',
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT (folder_key, file_id) DO UPDATE SET
                            claimed_at = CURRENT_TIMESTAMP,
                            updated_at = CASE
                                WHEN ? = 1 THEN updated_at
                                ELSE CURRENT_TIMESTAMP
                            END,
                            status = CASE
                                WHEN ? = 1
                                     AND status IN ('done', 'no_face')
                                THEN status
                                ELSE 'processing'
                            END
                        WHERE (claimed_at IS NULL
                               OR claimed_at < datetime('now', ?))
                          AND (? = 1
                               OR status NOT IN ('done', 'no_face'))
                        RETURNING file_id
                        """,
                    "params": [
                        folder_key,
                        file_id,
                        force_value,
                        force_value,
                        stale,
                        force_value,
                    ],
                }
            )

        if not statements:
            return set()

        claimed: set[str] = set()
        for result in self._batch(statements):
            for row in result.get("results") or []:
                file_id = row.get("file_id")
                if file_id:
                    claimed.add(str(file_id))
        return claimed

    # ------------------------------------------------------------- folder meta

    def set_folder_meta(self, folder_key: str, key: str, value: str) -> None:
        self._ensure_schema()
        self._query(
            """
            INSERT INTO drive_folders (folder_key, meta, updated_at)
            VALUES (?, json_object(?, ?), CURRENT_TIMESTAMP)
            ON CONFLICT (folder_key) DO UPDATE SET
                meta = json_patch(
                    drive_folders.meta,
                    json_object(?, ?)
                ),
                updated_at = CURRENT_TIMESTAMP
            """,
            (folder_key, key, str(value), key, str(value)),
        )

    def set_folder_meta_dict(
        self, folder_key: str, meta: dict[str, Any]
    ) -> None:
        """Tüm meta nesnesini tek seferde yazar (migration için)."""
        self._ensure_schema()
        self._query(
            """
            INSERT INTO drive_folders (folder_key, meta, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (folder_key) DO UPDATE SET
                meta = excluded.meta,
                updated_at = CURRENT_TIMESTAMP
            """,
            (folder_key, json.dumps(meta or {}, ensure_ascii=False)),
        )

    def get_folder_meta(
        self, folder_key: str, key: str, default: str | None = None
    ) -> str | None:
        self._ensure_schema()
        rows = self._query(
            """
            SELECT json_extract(meta, '$.' || ?) AS value
            FROM drive_folders WHERE folder_key = ?
            """,
            (key, folder_key),
        )
        if not rows or rows[0].get("value") is None:
            return default
        return str(rows[0].get("value"))

    def get_folder_meta_dict(self, folder_key: str) -> dict:
        self._ensure_schema()
        rows = self._query(
            "SELECT meta FROM drive_folders WHERE folder_key = ?",
            (folder_key,),
        )
        if not rows:
            return {}
        meta = rows[0].get("meta")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except ValueError:
                return {}
        return dict(meta or {})

    def list_folders(self) -> list[dict]:
        self._ensure_schema()
        rows = self._query("SELECT folder_key, meta FROM drive_folders")
        output: list[dict] = []
        for row in rows:
            meta = row.get("meta")
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except ValueError:
                    meta = {}
            output.append(
                {
                    "folder_key": str(row.get("folder_key") or ""),
                    "meta": meta or {},
                }
            )
        return output

    def delete_folder_meta(self, folder_key: str) -> None:
        self._ensure_schema()
        self._query(
            "DELETE FROM drive_folders WHERE folder_key = ?",
            (folder_key,),
        )

    # -------------------------------------------------------- indexed folders

    def register_indexed_folders(
        self, folder_ids: list[str], root_key: str
    ) -> int:
        ids = [str(folder_id) for folder_id in folder_ids if folder_id]
        if not ids:
            return 0
        self._ensure_schema()

        statements = [
            {
                "sql": """
                    INSERT INTO drive_indexed_folders
                        (folder_id, root_key, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT (folder_id) DO UPDATE SET
                        root_key = excluded.root_key,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                "params": [folder_id, root_key],
            }
            for folder_id in ids
        ]
        self._batch(statements)
        return len(ids)

    def is_indexed_folder(self, folder_id: str) -> bool:
        if not folder_id:
            return False
        self._ensure_schema()
        rows = self._query(
            """
            SELECT 1 AS found FROM drive_indexed_folders
            WHERE folder_id = ? LIMIT 1
            """,
            (folder_id,),
        )
        return bool(rows)

    # ------------------------------------------------------------------ misc

    def clear_folder(self, folder_key: str) -> None:
        self._ensure_schema()
        self._batch(
            [
                {
                    "sql": f"DELETE FROM {self.table} WHERE folder_key = ?",
                    "params": [folder_key],
                },
                {
                    "sql": "DELETE FROM drive_folders WHERE folder_key = ?",
                    "params": [folder_key],
                },
                {
                    "sql": (
                        "DELETE FROM drive_indexed_folders WHERE root_key = ?"
                    ),
                    "params": [folder_key],
                },
            ]
        )

    def close(self) -> None:
        session = getattr(self._local, "session", None)
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
            self._local.session = None
