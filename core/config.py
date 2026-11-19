from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

try:
    import streamlit as st
except ImportError:  # FastAPI / worker ortamında Streamlit kurulu olmayabilir.
    st = None  # type: ignore[assignment]

APP_TITLE = "Drive Yüz Tanıma Sistemi"
APP_BRAND = "BY OCAL"

EMBEDDING_SIZE = 128

MODEL_DIR = Path(os.environ.get("DRIVE_FACE_MODEL_DIR", "/tmp/drive_face_models"))

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"
YUNET_URLS = (
    "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/"
    f"face_detection_yunet/{YUNET_FILE}",
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    f"face_detection_yunet/{YUNET_FILE}",
)
SFACE_URLS = (
    "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/"
    f"face_recognition_sface/{SFACE_FILE}",
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    f"face_recognition_sface/{SFACE_FILE}",
)

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".jpe",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
    ".avif",
    ".cr2",
    ".cr3",
    ".nef",
    ".arw",
    ".dng",
    ".orf",
    ".raf",
    ".rw2",
}

DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

DEFAULT_THUMB_SIZE = 768
DEFAULT_DET_THRESHOLD = 0.60
DEFAULT_MIN_FACE = 40
DEFAULT_MAX_FACES = 8
DEFAULT_MATCH_THRESHOLD = 0.50

THUMB_OPTIONS = {
    "Hızlı (512 px)": 512,
    "Dengeli (768 px)": 768,
    "Yüksek kalite (1024 px)": 1024,
}


def _load_dotenv() -> None:
    """Küçük, bağımlılıksız .env yükleyici. Var olan env değerlerini ezmez."""
    for candidate in (Path(".env"), Path(__file__).resolve().parent.parent / ".env"):
        if not candidate.exists():
            continue
        try:
            for raw_line in candidate.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :]
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
        except OSError:
            continue
        break


_load_dotenv()


def get_secret(name: str, default: Any = None) -> Any:
    """Streamlit secrets -> environment -> default sırasıyla okur."""
    if st is not None:
        try:
            secret = st.secrets.get(name)  # type: ignore[attr-defined]
            if secret not in (None, ""):
                return secret
        except Exception:
            pass
    value = os.environ.get(name)
    return default if value in (None, "") else value


def get_service_account_info() -> dict[str, Any] | None:
    """Service account bilgisini secrets, JSON env, dosya env veya yerel dosyadan bulur."""
    if st is not None:
        try:
            if "gcp_service_account" in st.secrets:
                info = dict(st.secrets["gcp_service_account"])
                if info.get("type") == "service_account" and info.get("private_key"):
                    info["private_key"] = str(info["private_key"]).replace("\\n", "\n")
                    return info
        except Exception:
            pass

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        try:
            info = json.loads(raw)
            if info.get("type") == "service_account":
                return info
        except (TypeError, ValueError):
            pass

    for env_name in ("GOOGLE_APPLICATION_CREDENTIALS", "GCP_CREDENTIALS_FILE"):
        path_value = os.environ.get(env_name)
        if not path_value:
            continue
        path = Path(path_value)
        if path.exists():
            try:
                info = json.loads(path.read_text(encoding="utf-8"))
                if info.get("type") == "service_account":
                    return info
            except (OSError, ValueError):
                pass

    local = Path(__file__).resolve().parent.parent / "credentials.json"
    if local.exists():
        try:
            info = json.loads(local.read_text(encoding="utf-8"))
            if info.get("type") == "service_account":
                return info
        except (OSError, ValueError):
            pass

    return None


def _local_secrets() -> dict[str, Any]:
    """Streamlit dışında (ör. ``indexer.py``) secrets.toml dosyasını okur."""
    for candidate in (
        Path(".streamlit/secrets.toml"),
        Path(__file__).resolve().parent.parent / ".streamlit/secrets.toml",
    ):
        if not candidate.exists():
            continue
        try:
            import tomllib

            with candidate.open("rb") as handle:
                data = tomllib.load(handle)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _d1_section() -> dict[str, Any]:
    """``[cloudflare_d1]`` tablosunu Streamlit secrets veya dosyadan okur."""
    if st is not None:
        try:
            if "cloudflare_d1" in st.secrets:
                section = dict(st.secrets["cloudflare_d1"])
                if section:
                    return section
        except Exception:
            pass

    local = _local_secrets().get("cloudflare_d1")
    return dict(local) if isinstance(local, dict) else {}


def get_d1_config() -> dict[str, Any] | None:
    """Cloudflare D1 bağlantı bilgisini secrets/env üzerinden okur.

    Tek düz anahtarlar veya ``[cloudflare_d1]`` tablosu kullanılabilir::

        CLOUDFLARE_ACCOUNT_ID
        CLOUDFLARE_D1_DATABASE_ID
        CLOUDFLARE_D1_API_TOKEN
    """
    section = _d1_section()
    local = _local_secrets()

    def pick(*names: str) -> str | None:
        for name in names:
            value = get_secret(name)
            if value in (None, ""):
                value = local.get(name)
            if value not in (None, ""):
                return str(value)
        return None

    account_id = pick(
        "CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT_ID", "D1_ACCOUNT_ID"
    ) or section.get("account_id")
    database_id = pick(
        "CLOUDFLARE_D1_DATABASE_ID", "CF_D1_DATABASE_ID", "D1_DATABASE_ID"
    ) or section.get("database_id")
    api_token = pick(
        "CLOUDFLARE_D1_API_TOKEN", "CLOUDFLARE_API_TOKEN", "CF_API_TOKEN"
    ) or section.get("api_token")

    if account_id and database_id and api_token:
        return {
            "account_id": str(account_id),
            "database_id": str(database_id),
            "api_token": str(api_token),
        }
    return None


def get_turso_config() -> dict[str, Any] | None:
    """Turso/libSQL bağlantı bilgisini env/secrets üzerinden okur."""
    def pick(*names: str) -> Any:
        for name in names:
            value = get_secret(name)
            if value not in (None, ""):
                return value
        return None

    database_url = pick("MOMENZ_TURSO_DATABASE_URL", "TURSO_DATABASE_URL")
    auth_token = pick("MOMENZ_TURSO_AUTH_TOKEN", "TURSO_AUTH_TOKEN")
    if database_url and auth_token:
        return {
            "database_url": str(database_url),
            "auth_token": str(auth_token),
        }
    return None


def get_storage_config() -> tuple[str | None, dict[str, Any] | None]:
    """Aktif veritabanı backend'ini seçer (Turso, eski D1 fallback)."""
    turso_config = get_turso_config()
    if turso_config:
        return "turso", turso_config
    d1_config = get_d1_config()
    if d1_config:
        return "d1", d1_config
    return None, None


def folder_key(
    folder_id: str,
    resource_key: str | None,
    include_subfolders: bool,
    thumb_size: int,
) -> str:
    raw = f"{folder_id}|{resource_key or ''}|{int(include_subfolders)}|{int(thumb_size)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def drive_view_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def drive_download_url(file_id: str) -> str:
    return f"https://drive.usercontent.google.com/download?id={file_id}&export=download"
