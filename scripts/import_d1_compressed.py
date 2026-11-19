"""Cloudflare D1 yedeğindeki drive_face_index'i sıkıştırılmış tek satıra çevirip Turso'ya yazar.

    python scripts/import_d1_compressed.py [--dump PATH] [--only FOLDER_KEY] [--dry-run]

Akış:
  1) D1 SQL dump'ındaki 71.294 drive_face_index satırı geçici SQLite'a yüklenir.
  2) Klasör başına tek ``files`` listesi oluşturulur; embedding'ler int8
     ``matrix`` alanına nicemlenir, ``files``/``metas`` zlib ile sıkıştırılır.
  3) Sonuç Turso ``folder_matrices`` tablosuna KLASÖR BAŞINA TEK INSERT ile yazılır.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.config import get_settings
from api.db import TursoClient
from api.repositories import index as index_repo

DEFAULT_DUMP = "/tmp/opencode/momenz_d1.sql"
TEMP_DB = "/tmp/opencode/d1_index_import.sqlite"

_SCHEMA = """
CREATE TABLE drive_face_index (
  folder_key TEXT NOT NULL,
  file_id TEXT NOT NULL,
  name TEXT,
  path TEXT,
  width INTEGER NOT NULL DEFAULT 0,
  height INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'done',
  error TEXT,
  faces TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT,
  claimed_at TEXT,
  PRIMARY KEY (folder_key, file_id)
);
"""


class _Capture:

    def __init__(self) -> None:
        self.statement: tuple[str, tuple] | None = None

    def execute(self, sql: str, params=None) -> int:
        if sql.lstrip().upper().startswith("INSERT INTO FOLDER_MATRICES"):
            self.statement = (sql, tuple(params or ()))
        return 1

    def query_one(self, sql: str, params=None) -> dict | None:
        return None


def _load_dump(sql_path: Path, temp_path: Path) -> sqlite3.Connection:
    if temp_path.exists():
        temp_path.unlink()
    conn = sqlite3.connect(temp_path)
    conn.executescript(_SCHEMA)
    prefix = "INSERT INTO drive_face_index"
    loaded = 0
    with sql_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith(prefix):
                continue
            conn.execute(line.strip().rstrip(";"))
            loaded += 1
            if loaded % 5000 == 0:
                conn.commit()
                print(f"  D1 satırı yükleniyor: {loaded}", flush=True)
    conn.commit()
    print(f"D1 yedeğinden {loaded} satır yüklendi.", flush=True)
    return conn


def _folder_version(db: TursoClient, folder_key: str) -> int:
    for sql in (
        "SELECT version FROM folder_matrices WHERE folder_key = ? LIMIT 1",
        "SELECT version FROM folder_index_versions WHERE folder_key = ? LIMIT 1",
    ):
        row = db.query_one(sql, (folder_key,))
        if row and row.get("version") is not None:
            return int(row["version"] or 0)
    return 0


def _folder_meta(db: TursoClient, folder_key: str) -> dict:
    row = db.query_one(
        "SELECT meta FROM drive_folders WHERE folder_key = ? LIMIT 1", (folder_key,)
    ) or {}
    try:
        value = json.loads(str(row.get("meta") or "{}"))
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def _blob_sizes(params: tuple) -> tuple[int, int, int]:
    def size(value) -> int:
        if isinstance(value, (bytes, bytearray)):
            return len(value)
        return len(str(value or "").encode("utf-8"))

    return size(params[3]), size(params[4]), size(params[6])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", default=DEFAULT_DUMP)
    parser.add_argument("--only")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.db_ready():
        raise SystemExit("Turso ayarları eksik. .env dosyasını kontrol et.")

    sql_path = Path(args.dump)
    if not sql_path.exists():
        raise SystemExit(f"D1 dump bulunamadı: {sql_path}")

    print(f"D1 yedeği okunuyor: {sql_path}", flush=True)
    source = _load_dump(sql_path, Path(TEMP_DB))
    source.row_factory = sqlite3.Row

    db = None if args.dry_run else TursoClient(**settings.db_config)
    try:
        if db is not None:
            index_repo.ensure_folder_matrices(db)

        if args.only:
            folder_keys = [(args.only,)]
        else:
            folder_keys = source.execute(
                "SELECT DISTINCT folder_key FROM drive_face_index ORDER BY folder_key"
            ).fetchall()

        written = total_before = total_after = 0
        for number, key_row in enumerate(folder_keys, start=1):
            folder_key = str(key_row[0])
            rows = source.execute(
                """SELECT file_id, name, path, width, height, status, error,
                          faces, claimed_at
                   FROM drive_face_index WHERE folder_key = ? ORDER BY file_id""",
                (folder_key,),
            ).fetchall()
            if not rows:
                print(f"[{number}/{len(folder_keys)}] {folder_key}: veri yok", flush=True)
                continue

            files: list[dict] = []
            for row in rows:
                try:
                    faces = json.loads(str(row["faces"] or "[]"))
                    if not isinstance(faces, list):
                        faces = []
                except ValueError:
                    faces = []
                files.append(
                    {
                        "file_id": str(row["file_id"] or ""),
                        "name": str(row["name"] or ""),
                        "path": str(row["path"] or ""),
                        "width": int(row["width"] or 0),
                        "height": int(row["height"] or 0),
                        "status": str(row["status"] or "done"),
                        "error": row["error"],
                        "claimed_at": row["claimed_at"],
                        "faces": faces,
                    }
                )

            version = _folder_version(db, folder_key) if db is not None else 0
            meta = _folder_meta(db, folder_key) if db is not None else {}
            capture = _Capture()
            index_repo.save_index_row(capture, folder_key, version, files, meta)
            if capture.statement is None:
                raise RuntimeError(f"Sıkıştırılmış satır üretilemedi: {folder_key}")
            sql, params = capture.statement
            matrix_size, metas_size, files_size = _blob_sizes(params)
            before = sum(
                len(str(row["faces"] or "").encode("utf-8")) for row in rows
            )
            after = matrix_size + metas_size + files_size
            total_before += before
            total_after += after

            if db is not None:
                for attempt in range(1, 7):
                    try:
                        db.execute(sql, params)
                        break
                    except Exception as exc:
                        print(
                            f"  yazma denemesi {attempt}/6: {exc}", flush=True
                        )
                        if attempt == 6:
                            raise
                        time.sleep(2 * attempt)

            written += 1
            print(
                f"[{number}/{len(folder_keys)}] {folder_key}: "
                f"{len(files)} dosya | "
                f"D1 yüz JSON {before / 1048576:.1f} MB -> "
                f"sıkıştırılmış {after / 1048576:.1f} MB "
                f"(matrix {matrix_size / 1048576:.1f}, "
                f"metas {metas_size / 1048576:.1f}, "
                f"files {files_size / 1048576:.1f})",
                flush=True,
            )

        if db is not None and not args.only:
            db.execute(
                """
                UPDATE folder_matrices
                SET is_public = EXISTS(
                    SELECT 1 FROM events e
                    WHERE e.folder_key = folder_matrices.folder_key
                      AND e.is_public = 1
                )
                """
            )
            print("is_public bayrakları events'ten eşitlendi.", flush=True)

        print(
            f"{written} klasör tek satır olarak {'doğrulanacak' if args.dry_run else 'yazıldı'}.",
            flush=True,
        )
        print(
            f"TOPLAM yüz verisi: {total_before / 1048576:.1f} MB -> "
            f"{total_after / 1048576:.1f} MB",
            flush=True,
        )
    finally:
        if db is not None:
            db.close()
        source.close()


if __name__ == "__main__":
    main()
