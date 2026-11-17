#!/usr/bin/env python3
"""İlk yönetici hesabını oluşturur.

    python scripts/bootstrap_admin.py admin@momenz.com

Şifre MOMENZ_BOOTSTRAP_PASSWORD env'inden okunur; yoksa güvenli rastgele
üretilir ve ekrana yazılır. Üretimde MOMENZ_ENVIRONMENT=prod olmalıdır.
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.config import get_settings
from api.db import D1Client
from api.repositories import users as repo
from api.security import hash_password, new_id


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Kullanım: python scripts/bootstrap_admin.py <email>")
    email = sys.argv[1].strip().lower()
    settings = get_settings()
    if not settings.d1_ready():
        raise SystemExit("D1 ayarları eksik.")

    password = os.environ.get("MOMENZ_BOOTSTRAP_PASSWORD") or getpass.getpass(
        "Yönetici şifresi: "
    )
    if len(password) < 12:
        raise SystemExit("Şifre en az 12 karakter olmalı.")

    db = D1Client(**settings.d1_config)
    if repo.get_by_email(db, email):
        raise SystemExit("Bu e-posta zaten kayıtlı.")

    repo.create_user(
        db,
        user_id=new_id(),
        email=email,
        name="Admin",
        password_hash=hash_password(password),
        email_verified=True,
        role="admin",
    )
    print(f"Yönetici oluşturuldu: {email}")
    if "MOMENZ_BOOTSTRAP_PASSWORD" not in os.environ:
        print("Şifreyi güvenli bir yerde sakla.")


if __name__ == "__main__":
    main()
