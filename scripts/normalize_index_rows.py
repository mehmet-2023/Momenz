#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.config import get_settings
from api.db import TursoClient
from api.repositories import index as index_repo

_RETRIES = 6


def _client(settings):
    return TursoClient(**settings.db_config)


def _is_normalized(db: TursoClient, folder_key: str) -> bool:
    row = db.query_one(
        """
        SELECT rows AS face_rows, length(IFNULL(matrix, X'')) AS matrix_size,
               substr(IFNULL(files, X''), 1, 1) AS files_first
        FROM folder_matrices WHERE folder_key = ?
        """,
        (folder_key,),
    ) or {}
    # int8 matris = satır sayısı * 128 byte; zlib başlığı 0x78.
    return (
        int(row.get("matrix_size") or 0) == int(row.get("face_rows") or 0) * 128
        and row.get("files_first") in (b"\x78", 120, "x")
    )


def _sizes(db: TursoClient, folder_key: str) -> tuple[int, int, int]:
    row = db.query_one(
        """
        SELECT length(IFNULL(files, X'')) AS files_size,
               length(IFNULL(matrix, X'')) AS matrix_size,
               length(IFNULL(metas, X'')) AS metas_size
        FROM folder_matrices WHERE folder_key = ?
        """,
        (folder_key,),
    ) or {}
    return (
        int(row.get("files_size") or 0),
        int(row.get("matrix_size") or 0),
        int(row.get("metas_size") or 0),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="yalnızca bu folder_key")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.db_ready():
        raise SystemExit("Turso ayarları eksik. .env dosyasını kontrol et.")

    db = _client(settings)
    try:
        index_repo.ensure_folder_matrices(db)
        sql = "SELECT folder_key FROM folder_matrices"
        params: tuple = ()
        if args.only:
            sql += " WHERE folder_key = ?"
            params = (args.only,)
        folders = [
            str(row["folder_key"])
            for row in db.query(sql + " ORDER BY folder_key", params)
            if row.get("folder_key")
        ]
        if not folders:
            raise SystemExit("Normalize edilecek satır yok.")

        before_total = after_total = 0
        for number, folder_key in enumerate(folders, start=1):
            print(f"[{number}/{len(folders)}] {folder_key}", flush=True)
            before = _sizes(db, folder_key)
            if _is_normalized(db, folder_key):
                print("  ATLANDI: zaten sıkıştırılmış format", flush=True)
                before_total += sum(before)
                after_total += sum(before)
                continue

            for attempt in range(1, _RETRIES + 1):
                try:
                    loaded = index_repo.load_index_row(db, folder_key)
                    if loaded is None:
                        print("  ATLANDI: okunamadı (files boş)", flush=True)
                        break
                    version, files, meta = loaded
                    index_repo.save_index_row(db, folder_key, version, files, meta)
                    after = _sizes(db, folder_key)
                    before_total += sum(before)
                    after_total += sum(after)
                    print(
                        "  files %.1f -> %.1f MB | matrix %.1f -> %.1f MB "
                        "| metas %.1f -> %.1f MB"
                        % (
                            before[0] / 1048576, after[0] / 1048576,
                            before[1] / 1048576, after[1] / 1048576,
                            before[2] / 1048576, after[2] / 1048576,
                        ),
                        flush=True,
                    )
                    break
                except Exception as exc:
                    print(
                        f"  deneme {attempt}/{_RETRIES} başarısız: {exc}", flush=True
                    )
                    if attempt == _RETRIES:
                        raise
                    time.sleep(2 * attempt)
                    try:
                        db.close()
                    except Exception:
                        pass
                    db = _client(settings)
        print(
            "TOPLAM: %.1f MB -> %.1f MB (%%%.1f tasarruf)"
            % (
                before_total / 1048576,
                after_total / 1048576,
                100 * (1 - after_total / before_total) if before_total else 0,
            ),
            flush=True,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
