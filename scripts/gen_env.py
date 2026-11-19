#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

TEMPLATE = """# Momenz API — {environment}
# UYARI: Bu dosya .gitignore içindedir. Asla commit etme.

MOMENZ_ENVIRONMENT={environment}
MOMENZ_JWT_SECRET={jwt_secret}
MOMENZ_COOKIE_SECURE={cookie_secure}
MOMENZ_TRUSTED_HOSTS={trusted_hosts}
MOMENZ_CORS_ORIGINS={cors_origins}
MOMENZ_WEB_BASE_URL={web_base_url}

# Cloudflare D1
MOMENZ_D1_ACCOUNT_ID=
MOMENZ_D1_DATABASE_ID=
MOMENZ_D1_API_TOKEN=

# Google Drive (servis hesabı JSON'unu tek satırda yapıştır)
MOMENZ_GOOGLE_DRIVE_API_KEY=
MOMENZ_GOOGLE_SERVICE_ACCOUNT_JSON=

# Mail — yalnızca "şifremi unuttum" akışı
MOMENZ_RESEND_API_KEY=
MOMENZ_MAIL_RESET_URL=https://momenz.vercel.app/sifre-sifirla?token={token}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", default="dev")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    target = Path(".env")
    if target.exists() and not args.force:
        raise SystemExit(".env zaten var. Ezmek için --force kullan (yedek alınır).")
    if target.exists() and args.force:
        backup = target.with_suffix(".env.bak")
        target.replace(backup)
        print(f"Mevcut .env -> {backup}")

    is_prod = args.environment.lower() in {"prod", "production", "live"}
    content = TEMPLATE.format(
        environment=args.environment,
        jwt_secret=secrets.token_urlsafe(48),
        cookie_secure="true" if is_prod else "false",
        trusted_hosts=(
            "momenz.onrender.com,localhost"
            if is_prod
            else "localhost,127.0.0.1"
        ),
        cors_origins=(
            "https://momenz.vercel.app" if is_prod else "http://localhost:3000"
        ),
        web_base_url=(
            "https://momenz.vercel.app" if is_prod else "http://localhost:3000"
        ),
    )
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    print(f"{target} oluşturuldu (600 yetkisi). JWT secret rastgele üretildi.")


if __name__ == "__main__":
    main()
