#!/usr/bin/env python3
"""Turso ``folder_matrices`` tablosunu mevcutdrive_face_index verisinden doldurur.

    python scripts/backfill_turso.py

Arama yolu artık yüz embedding'lerini satır satır okumaz; bu script klasör
başına tek BLOB yazar. Indexleme sonrası worker aynı yazımı incremental olarak
yapar; bu script yalnızca migrasyon anında kullanılır.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.config import get_settings
from api.db import TursoClient
from api.repositories import index as index_repo


def main() -> None:
    settings = get_settings()
    if not settings.db_ready():
        raise SystemExit("Turso ayarları eksik. .env dosyasını kontrol et.")

    db = TursoClient(**settings.db_config)
    try:
        index_repo.ensure_folder_matrices(db)
        rows = db.query(
            """
            SELECT folder_key FROM drive_face_index
            UNION
            SELECT folder_key FROM folder_index_versions
            ORDER BY folder_key
            """
        )
        folders = [str(row["folder_key"]) for row in rows if row.get("folder_key")]
        print(f"{len(folders)} klasör için matris hazırlanacak.")

        for number, folder_key in enumerate(folders, start=1):
            started = time.perf_counter()
            version_row = db.query_one(
                "SELECT version FROM folder_index_versions WHERE folder_key = ? LIMIT 1",
                (folder_key,),
            )
            version = int((version_row or {}).get("version") or 0)
            existing = index_repo.load_matrix(db, folder_key, version)
            if existing is not None:
                print(f"[{number}/{len(folders)}] {folder_key} v{version}: zaten güncel")
                continue
            matrix, metas = index_repo.fetch_matrix(db, folder_key)
            index_repo.save_matrix(db, folder_key, version, matrix, metas)
            elapsed = time.perf_counter() - started
            print(
                f"[{number}/{len(folders)}] {folder_key} v{version}: "
                f"{len(metas)} yüz, {matrix.nbytes / 1024 / 1024:.1f} MB, {elapsed:.1f}s"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
