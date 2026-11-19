"""Modal 'momenz' secret'ini yerel .env dosyasından oluşturur/günceller.

Kullanım (önce `modal token new` ile giriş yapılmış olmalı):
    .venv-modal/bin/python scripts/setup_modal_secret.py
    .venv-modal/bin/modal deploy worker/index_job.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODAL = ROOT / ".venv-modal" / "bin" / "modal"

KEYS = (
    "MOMENZ_TURSO_DATABASE_URL",
    "MOMENZ_TURSO_AUTH_TOKEN",
    "MOMENZ_GOOGLE_SERVICE_ACCOUNT_JSON",
    "MOMENZ_ENVIRONMENT",
    # Settings.prod doğrulaması bunları da istiyor; worker JWT kullanmasa bile
    # get_settings() çağrısı prod modda patlıyordu.
    "MOMENZ_JWT_SECRET",
    "MOMENZ_COOKIE_SECURE",
)


def _read_env(path: Path) -> dict[str, str]:
    """Minimal .env okuyucu (python-dotenv bağımlılığı olmadan)."""
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key.strip()] = value
    return result


def main() -> None:
    if not MODAL.exists():
        raise SystemExit("Modal CLI bulunamadı: .venv-modal/bin/modal")
    values = _read_env(ROOT / ".env")
    pairs: list[str] = []
    for key in KEYS:
        default = {
            "MOMENZ_ENVIRONMENT": "prod",
            "MOMENZ_COOKIE_SECURE": "true",
        }.get(key, "")
        value = values.get(key) or default
        if not value:
            raise SystemExit(f".env içinde {key} eksik.")
        # .env yerel geliştirme için cookie_secure=false içeriyor; Modal prod
        # ortamında bu değer Settings doğrulamasını doğrudan reddediyor.
        if key == "MOMENZ_COOKIE_SECURE":
            value = "true"
        if key == "MOMENZ_JWT_SECRET" and len(value) < 32:
            raise SystemExit("MOMENZ_JWT_SECRET en az 32 karakter olmalı.")
        pairs.append(f"{key}={value}")

    try:
        subprocess.run(
            [str(MODAL), "secret", "create", "momenz", *pairs, "--force"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        # Komut argümanlarında secret'lar var; traceback'i ASLA yazdırma.
        detail = (exc.stderr or "").strip().splitlines()
        message = detail[-1] if detail else "bilinmeyen hata"
        raise SystemExit(f"Modal secret oluşturulamadı: {message}") from None
    print("Modal secret 'momenz' güncellendi.")


if __name__ == "__main__":
    main()
