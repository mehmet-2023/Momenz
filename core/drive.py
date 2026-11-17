from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import numpy as np
import requests
from bs4 import BeautifulSoup

try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account

    _GOOGLE_AUTH_AVAILABLE = True
except Exception:  # pragma: no cover - requirements.txt kuruluysa girmez
    service_account = None  # type: ignore[assignment]
    GoogleAuthRequest = None  # type: ignore[assignment]
    _GOOGLE_AUTH_AVAILABLE = False

from .config import (
    DRIVE_FOLDER_MIME,
    DRIVE_SCOPE,
    IMAGE_EXTENSIONS,
)
from .image_utils import decode_image_bytes, encode_jpeg_bytes

_FOLDER_RE = re.compile(r"/folders/([-\w]{10,})")
_ID_QUERY_RE = re.compile(r"[?&]id=([-\w]{10,})")
_RESOURCE_KEY_RE = re.compile(r"[?&]resourcekey=([-\w]{10,})")
_RAW_ID_RE = re.compile(r"^[-\w]{10,}$")
_FILE_RE = re.compile(r"/file/d/([-\w]{10,})")
_ANY_FOLDER_RE = re.compile(r"/folders/([-\w]{10,})")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class DriveError(Exception):
    """Drive erişimi / listeleme hataları için okunabilir istisna."""


@dataclass(slots=True)
class DriveItem:
    id: str
    name: str
    mime_type: str = ""
    path: str = ""
    size: int = 0

    @property
    def is_folder(self) -> bool:
        return self.mime_type == DRIVE_FOLDER_MIME


def parse_drive_folder_url(url: str) -> tuple[str, str | None]:
    """Drive klasör linkinden (folder_id, resource_key) çıkarır."""
    text = (url or "").strip()
    if not text:
        raise DriveError("Lütfen bir Google Drive klasör linki girin.")

    if _RAW_ID_RE.match(text):
        return text, None

    resource_match = _RESOURCE_KEY_RE.search(text)
    resource_key = resource_match.group(1) if resource_match else None

    folder_match = _FOLDER_RE.search(text)
    if folder_match:
        return folder_match.group(1), resource_key

    id_match = _ID_QUERY_RE.search(text)
    if id_match:
        return id_match.group(1), resource_key

    if "/file/d/" in text:
        raise DriveError(
            "Bu bir dosya linki. Lütfen klasör linki kullanın "
            "(https://drive.google.com/drive/folders/...)."
        )

    raise DriveError(
        "Linkten klasör kimliği okunamadı. Örnek: "
        "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp"
    )


class DriveClient:
    """Google Drive klasörlerini listeler ve görselleri doğrudan thumbnail olarak indirir."""

    def __init__(
        self,
        api_key: str | None = None,
        service_account_info: dict | None = None,
        timeout: tuple[float, float] = (10.0, 40.0),
        max_retries: int = 4,
    ) -> None:
        self.api_key = (api_key or "").strip() or None
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.warnings: list[str] = []
        self.folder_title: str | None = None
        self.service_account_email: str | None = None
        self._thread_local = threading.local()
        self._token_lock = threading.Lock()
        self._creds = None

        if service_account_info:
            if not _GOOGLE_AUTH_AVAILABLE:
                raise DriveError(
                    "google-auth kurulu değil. requirements.txt dosyasını yükleyin."
                )
            try:
                self._creds = service_account.Credentials.from_service_account_info(  # type: ignore[union-attr]
                    service_account_info,
                    scopes=[DRIVE_SCOPE],
                )
                self.service_account_email = service_account_info.get("client_email")
            except Exception as exc:
                raise DriveError(f"Service account okunamadı: {exc}") from exc

    @property
    def auth_label(self) -> str:
        if self._creds is not None:
            return f"Service account ({self.service_account_email or 'aktif'})"
        if self.api_key:
            return "Drive API anahtarı"
        return "Anahtarsız public HTML"

    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": _USER_AGENT,
                    "Referer": "https://drive.google.com/",
                    "Accept": "*/*",
                }
            )
            self._thread_local.session = session
        return session

    def _get_token(self, force: bool = False) -> str | None:
        if self._creds is None:
            return None
        with self._token_lock:
            if force or not self._creds.valid or self._creds.expired:
                self._creds.refresh(GoogleAuthRequest())  # type: ignore[misc]
            return self._creds.token

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        auth: bool = False,
        retries: int | None = None,
        allow_403_retry: bool = True,
        **kwargs,
    ) -> requests.Response:
        attempts = (self.max_retries if retries is None else int(retries)) + 1
        last_error: Exception | None = None
        last_response: requests.Response | None = None

        for attempt in range(attempts):
            request_headers = dict(headers or {})
            if auth:
                token = self._get_token()
                if token:
                    request_headers["Authorization"] = f"Bearer {token}"

            try:
                response = self._session().request(
                    method,
                    url,
                    params=params,
                    headers=request_headers,
                    timeout=self.timeout,
                    **kwargs,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(min(1.2 * (2**attempt), 8.0))
                continue

            last_response = response

            if response.status_code == 401 and auth and self._creds is not None and attempt == 0:
                try:
                    self._get_token(force=True)
                except Exception:
                    pass
                continue

            if response.status_code in (429, 500, 502, 503, 504):
                if attempt + 1 < attempts:
                    time.sleep(min(1.2 * (2**attempt), 8.0))
                    continue

            if (
                response.status_code == 403
                and allow_403_retry
                and attempt < min(2, attempts - 1)
            ):
                time.sleep(1.0 + attempt)
                continue

            return response

        if last_response is not None:
            return last_response
        raise DriveError(f"Google Drive isteği başarısız oldu: {last_error}")

    # ------------------------------------------------------------------ listing

    def list_children(
        self, folder_id: str, resource_key: str | None = None
    ) -> list[DriveItem]:
        api_error: DriveError | None = None

        if self._creds is not None or self.api_key:
            try:
                return self._list_children_api(folder_id)
            except DriveError as exc:
                api_error = exc
                self.warnings.append(
                    f"Drive API listelemesi başarısız oldu, anahtarsız yönteme geçildi: {exc}"
                )

        try:
            return self._list_children_embedded(folder_id, resource_key)
        except DriveError as exc:
            if api_error is not None:
                raise DriveError(f"{exc}\n\nDrive API ayrıntısı: {api_error}") from exc
            raise

    def get_folder_meta(self, folder_id: str) -> dict:
        """Klasörün adını ve Drive tarihlerini (yükleme/oluşturma) döndürür."""
        if self._creds is None and not self.api_key:
            return {}

        params: dict = {
            "fields": "id,name,createdTime,modifiedTime",
            "supportsAllDrives": "true",
        }
        if self._creds is None:
            params["key"] = self.api_key

        try:
            response = self._request(
                "GET",
                f"https://www.googleapis.com/drive/v3/files/{folder_id}",
                params=params,
                headers={"Accept": "application/json"},
                auth=self._creds is not None,
            )
        except DriveError:
            return {}

        if response.status_code != 200:
            return {}

        try:
            payload = response.json()
        except ValueError:
            return {}

        return {
            "name": str(payload.get("name") or ""),
            "created_time": str(payload.get("createdTime") or ""),
            "modified_time": str(payload.get("modifiedTime") or ""),
        }

    def _get_file_parents(self, file_id: str) -> list[str]:
        if self._creds is None and not self.api_key:
            return []

        params: dict = {"fields": "parents", "supportsAllDrives": "true"}
        if self._creds is None:
            params["key"] = self.api_key

        try:
            response = self._request(
                "GET",
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                params=params,
                headers={"Accept": "application/json"},
                auth=self._creds is not None,
            )
        except DriveError:
            return []

        if response.status_code != 200:
            return []
        try:
            return list(response.json().get("parents") or [])
        except ValueError:
            return []

    def resolve_folder_from_file(self, file_id: str, depth: int) -> dict:
        """Bir dosyadan yukarı yürüyerek kök klasörü ve metasını döndürür."""
        current = file_id
        for _ in range(max(0, int(depth)) + 1):
            parents = self._get_file_parents(current)
            if not parents:
                return {}
            current = parents[0]

        meta = self.get_folder_meta(current)
        if not meta:
            return {}
        meta["id"] = current
        return meta

    def count_images(
        self,
        folder_id: str,
        resource_key: str | None = None,
        include_subfolders: bool = True,
    ) -> int:
        """Klasördeki (alt klasörler dahil) fotoğraf sayısını döndürür."""
        seen: set[str] = set()
        for item in self.walk_images(
            folder_id,
            include_subfolders=include_subfolders,
            resource_key=resource_key,
        ):
            seen.add(item.id)
        return len(seen)

    def _list_children_api(self, folder_id: str) -> list[DriveItem]:
        url = "https://www.googleapis.com/drive/v3/files"
        params: dict = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType,size)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "orderBy": "name_natural",
        }
        if self._creds is None:
            params["key"] = self.api_key

        items: list[DriveItem] = []
        page_token: str | None = None

        while True:
            if page_token:
                params["pageToken"] = page_token

            response = self._request(
                "GET",
                url,
                params=params,
                headers={"Accept": "application/json"},
                auth=self._creds is not None,
            )

            if response.status_code == 404:
                raise DriveError(
                    "Klasör bulunamadı veya bu kimliğin erişim izni yok."
                )
            if response.status_code in (401, 403):
                hint = ""
                if self.service_account_email:
                    hint = (
                        f" Klasörü {self.service_account_email} adresine "
                        "'Görüntüleyen' olarak paylaşabilirsiniz."
                    )
                raise DriveError(
                    f"Drive API erişimi reddedildi (HTTP {response.status_code}).{hint}"
                )
            if response.status_code >= 400:
                raise DriveError(
                    f"Drive API hatası (HTTP {response.status_code}): "
                    f"{response.text[:240]}"
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise DriveError("Drive API geçersiz JSON döndürdü.") from exc

            for file_data in payload.get("files", []):
                file_id = str(file_data.get("id", "")).strip()
                if not file_id:
                    continue
                items.append(
                    DriveItem(
                        id=file_id,
                        name=str(file_data.get("name") or "Adsız"),
                        mime_type=str(file_data.get("mimeType") or ""),
                        size=int(file_data.get("size") or 0),
                    )
                )

            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        return items

    def _list_children_embedded(
        self, folder_id: str, resource_key: str | None = None
    ) -> list[DriveItem]:
        params: dict = {"id": folder_id}
        if resource_key:
            params["resourcekey"] = resource_key

        response = self._request(
            "GET",
            "https://drive.google.com/embeddedfolderview",
            params=params,
            headers={"Accept": "text/html,application/xhtml+xml"},
        )

        if response.status_code != 200:
            raise DriveError(
                "Drive klasörü listelenemedi "
                f"(HTTP {response.status_code}). Klasörün "
                "'Bağlantıya sahip herkes' olarak paylaşıldığından emin olun."
            )

        text = response.text or ""
        lowered = text.lower()
        if "servicelogin" in lowered or "you need permission" in lowered:
            raise DriveError(
                "Klasör herkese açık değil. Google Drive'da klasörü "
                "'Bağlantıya sahip herkes → Görüntüleyen' yapın."
            )

        soup = BeautifulSoup(text, "html.parser")
        if soup.title and soup.title.string:
            self.folder_title = soup.title.string.strip()

        items: list[DriveItem] = []
        seen: set[tuple[str, str]] = set()

        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            if not isinstance(href, str) or not href:
                continue
            if "docs.google.com" in href:
                continue

            name = anchor.get_text(" ", strip=True) or "Adsız"

            file_match = _FILE_RE.search(href)
            if file_match:
                file_id = file_match.group(1)
                marker = ("file", file_id)
                if marker in seen:
                    continue
                seen.add(marker)
                items.append(DriveItem(id=file_id, name=name))
                continue

            folder_match = _ANY_FOLDER_RE.search(href)
            if folder_match:
                child_id = folder_match.group(1)
                if child_id == folder_id:
                    continue
                marker = ("folder", child_id)
                if marker in seen:
                    continue
                seen.add(marker)
                items.append(
                    DriveItem(
                        id=child_id,
                        name=name,
                        mime_type=DRIVE_FOLDER_MIME,
                    )
                )

        return items

    def walk_images(
        self,
        root_folder_id: str,
        include_subfolders: bool = True,
        resource_key: str | None = None,
        max_folders: int = 20000,
        max_depth: int = 100,
        on_folder: "Callable[[str], None] | None" = None,
    ) -> Iterator[DriveItem]:
        stack: list[tuple[str, str, str | None, int]] = [
            (root_folder_id, "", resource_key, 0)
        ]
        visited: set[str] = set()

        while stack:
            folder_id, path, folder_resource_key, depth = stack.pop()
            if folder_id in visited:
                continue
            visited.add(folder_id)
            if on_folder is not None:
                on_folder(folder_id)

            if len(visited) > max_folders:
                self.warnings.append(
                    f"Klasör limiti ({max_folders}) aşıldı; kalan alt klasörler atlandı."
                )
                break

            children = self.list_children(folder_id, folder_resource_key)
            for child in children:
                child_path = f"{path} / {child.name}" if path else child.name
                if child.is_folder:
                    if include_subfolders and depth < max_depth:
                        stack.append((child.id, child_path, None, depth + 1))
                    continue
                if self._looks_like_image(child):
                    yield DriveItem(
                        id=child.id,
                        name=child.name,
                        mime_type=child.mime_type,
                        path=child_path,
                        size=child.size,
                    )

    @staticmethod
    def _looks_like_image(item: DriveItem) -> bool:
        if item.mime_type.startswith("image/"):
            return True
        if item.mime_type and not item.mime_type.startswith("image/"):
            if item.mime_type != "application/octet-stream":
                return False
        suffix = Path(item.name).suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            return True
        if not suffix:
            return True
        return False

    # ------------------------------------------------------------------ fetching

    def fetch_image(
        self, file_id: str, size: int = 768, resource_key: str | None = None
    ) -> np.ndarray | None:
        """Görseli tam dosyayı indirmeden Drive thumbnail'ları üzerinden getirir."""
        size = max(256, min(int(size), 2048))
        candidates: list[tuple[str, dict | None, bool]] = []

        thumb_params: dict = {"id": file_id, "sz": f"w{size}"}
        if resource_key:
            thumb_params["resourcekey"] = resource_key
        candidates.append(
            ("https://drive.google.com/thumbnail", thumb_params, True)
        )

        if resource_key:
            candidates.append(
                (
                    "https://drive.google.com/thumbnail",
                    {"id": file_id, "sz": f"w{size}"},
                    True,
                )
            )

        for host in ("lh3", "lh4", "lh5", "lh6"):
            candidates.append(
                (
                    f"https://{host}.googleusercontent.com/d/{file_id}=w{size}",
                    None,
                    False,
                )
            )

        if self._creds is not None or self.api_key:
            media_params: dict = {"alt": "media", "supportsAllDrives": "true"}
            if self._creds is None:
                media_params["key"] = self.api_key
            candidates.append(
                (
                    f"https://www.googleapis.com/drive/v3/files/{file_id}",
                    media_params,
                    self._creds is not None,
                )
            )

        for url, params, use_auth in candidates:
            try:
                response = self._request(
                    "GET",
                    url,
                    params=params,
                    auth=use_auth and self._creds is not None,
                    headers={"Accept": "image/*,*/*;q=0.8"},
                )
            except DriveError:
                continue

            if response.status_code != 200:
                continue

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                continue

            data = response.content
            if not data or len(data) < 1024:
                continue
            head = data[:32].lstrip().lower()
            if head.startswith(b"<!doctype") or head.startswith(b"<html"):
                continue

            image = decode_image_bytes(data)
            if image is not None:
                return image

        return None

    def fetch_file_bytes(
        self, file_id: str, resource_key: str | None = None
    ) -> tuple[bytes, str] | None:
        """Görselin orijinal (normal kalite) baytlarını ve MIME türünü getirir."""
        candidates: list[tuple[str, dict, bool]] = []

        if self._creds is not None or self.api_key:
            media_params: dict = {"alt": "media", "supportsAllDrives": "true"}
            if self._creds is None:
                media_params["key"] = self.api_key
            candidates.append(
                (
                    f"https://www.googleapis.com/drive/v3/files/{file_id}",
                    media_params,
                    self._creds is not None,
                )
            )

        download_params: dict = {"id": file_id, "export": "download"}
        if resource_key:
            download_params["resourcekey"] = resource_key
        candidates.append(
            ("https://drive.usercontent.google.com/download", download_params, False)
        )

        for url, params, use_auth in candidates:
            try:
                response = self._request(
                    "GET",
                    url,
                    params=params,
                    auth=use_auth and self._creds is not None,
                    headers={"Accept": "image/*,*/*;q=0.8"},
                )
            except DriveError:
                continue

            if response.status_code != 200:
                continue

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                continue

            data = response.content
            if not data or len(data) < 1024:
                continue
            head = data[:32].lstrip().lower()
            if head.startswith(b"<!doctype") or head.startswith(b"<html"):
                continue

            if decode_image_bytes(data) is not None:
                mime = content_type.split(";")[0].strip() or "application/octet-stream"
                return data, mime

        fallback = self.fetch_image(file_id, 2048, resource_key)
        if fallback is not None:
            encoded = encode_jpeg_bytes(fallback)
            if encoded:
                return encoded, "image/jpeg"

        return None
