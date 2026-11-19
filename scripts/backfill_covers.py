#!/usr/bin/env python3
"""Mevcut folder_matrices satırları için etkinlik kapağını geriye doldur.

Kapak seçimi yeni index yazımlarında otomatik yapılır; bu script yalnızca
önceden oluşturulmuş satırlarda `cover_file_id` boşsa çalıştırılır. Tam index
yeniden yazılmaz; yalnızca tek sütun güncellenir.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.config import get_settings
from api.db import TursoClient
from api.repositories import index as index_repo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="yalnızca bu folder_key")
    parser.add_argument(
        "--force",
        action="store_true",
        help="kapak zaten dolu olsa da yeniden seç",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.db_ready():
        raise SystemExit("Turso ayarları eksik. .env dosyasını kontrol et.")

    db = TursoClient(**settings.db_config)
    try:
        index_repo.ensure_folder_matrices(db)
        sql = "SELECT folder_key, cover_file_id FROM folder_matrices"
        params: tuple = ()
        if args.only:
            sql += " WHERE folder_key = ?"
            params = (args.only,)
        rows = db.query(sql + " ORDER BY folder_key", params)
        if not rows:
            raise SystemExit("Güncellenecek klasör satırı yok.")

        updated = skipped = 0
        for row in rows:
            folder_key = str(row.get("folder_key") or "")
            if not folder_key:
                continue
            if not args.force and str(row.get("cover_file_id") or ""):
                skipped += 1
                continue
            files = index_repo.folder_files(db, folder_key)
            cover = index_repo.select_cover_file_id(files)
            if not cover:
                print(f"  ATLANDI: {folder_key} (dosya yok)")
                skipped += 1
                continue
            db.execute(
                "UPDATE folder_matrices SET cover_file_id = ? WHERE folder_key = ?",
                (cover, folder_key),
            )
            index_repo.invalidate_files_cache(folder_key)
            print(f"  {folder_key} -> {cover}")
            updated += 1
        print(f"TOPLAM: {updated} güncellendi, {skipped} atlandı")
    finally:
        db.close()


if __name__ == "__main__":
    main()
