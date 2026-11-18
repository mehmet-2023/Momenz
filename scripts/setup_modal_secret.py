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
    "MOMENZ_D1_ACCOUNT_ID",
    "MOMENZ_D1_DATABASE_ID",
    "MOMENZ_D1_API_TOKEN",
    "MOMENZ_GOOGLE_SERVICE_ACCOUNT_JSON",
    "MOMENZ_ENVIRONMENT",
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
        value = values.get(key) or ("prod" if key == "MOMENZ_ENVIRONMENT" else "")
        if not value:
            raise SystemExit(f".env içinde {key} eksik.")
        pairs.append(f"{key}={value}")

    subprocess.run(
        [str(MODAL), "secret", "create", "momenz", *pairs, "--force"],
        cwd=ROOT,
        check=True,
    )
    print("Modal secret 'momenz' güncellendi.")


if __name__ == "__main__":
    main()
