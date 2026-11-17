#!/usr/bin/env python3
"""D1 şema migration'larını uygular (idempotent).

    python scripts/migrate.py

Ortam değişkenleri: MOMENZ_D1_ACCOUNT_ID / DATABASE_ID / API_TOKEN
"""
from __future__ import annotations

from pathlib import Path

from api.config import get_settings
from api.db import D1Client

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def split_statements(sql: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            parts.append("\n".join(current).strip())
            current = []
    if current:
        parts.append("\n".join(current).strip())
    return [item for item in parts if item]


def main() -> None:
    settings = get_settings()
    if not settings.d1_ready():
        raise SystemExit("D1 ayarları eksik. .env dosyasını kontrol et.")
    db = D1Client(**settings.d1_config)
    db.execute(
        "CREATE TABLE IF NOT EXISTS momenz_migrations "
        "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    applied = {
        str(row["name"])
        for row in db.query("SELECT name FROM momenz_migrations")
    }

    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in applied:
            print(f"✓ {path.name} (zaten uygulanmış)")
            continue
        for statement in split_statements(path.read_text(encoding="utf-8")):
            try:
                db.execute(statement)
            except Exception as exc:
                message = str(exc).lower()
                # ALTER sırasında kolon varsa geç (yarım kalmış migration).
                if "duplicate column name" in message or "already exists" in message:
                    continue
                raise SystemExit(f"{path.name}: {exc}\nSQL: {statement[:200]}")
        db.execute(
            "INSERT INTO momenz_migrations (name) VALUES (?)", (path.name,)
        )
        print(f"✓ {path.name} uygulandı")


if __name__ == "__main__":
    main()
