#!/usr/bin/env python3
"""folder_matrices tek satırlık index'ini doğrular (idempotent).

    python scripts/backfill_turso.py

Eski drive_face_index tablosu kaldırıldı; yeni klasörlerin satırını worker
oluşturur. Bu script yalnızca mevcut satırların ``files`` alanının dolu
olduğunu kontrol eder, eksikse worker'ın ilgili job'u çalıştırması gerekir.
"""
from __future__ import annotations

import sys
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
            SELECT folder_key FROM folder_matrices
            UNION
            SELECT folder_key FROM folder_index_versions
            ORDER BY folder_key
            """
        )
        folders = [str(row["folder_key"]) for row in rows if row.get("folder_key")]
        missing: list[str] = []
        print(f"{len(folders)} klasör kontrol ediliyor.")
        for number, folder_key in enumerate(folders, start=1):
            loaded = index_repo.load_index_row(db, folder_key)
            if loaded is None:
                missing.append(folder_key)
                print(f"[{number}/{len(folders)}] {folder_key}: EKSİK (worker indexlemeli)")
            else:
                print(
                    f"[{number}/{len(folders)}] {folder_key}: v{loaded[0]}, "
                    f"{len(loaded[1])} dosya"
                )
        if missing:
            raise SystemExit(f"Eksik klasörler: {', '.join(missing)}")
        print("Tüm klasörler tek satırlık index ile hazır.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
