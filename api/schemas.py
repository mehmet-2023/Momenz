from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints
from typing import Annotated

_FileId = Annotated[str, StringConstraints(max_length=255, strip_whitespace=True)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str | None = None  


class PasswordResetIn(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(ORMModel):
    id: str
    email: EmailStr
    name: str | None = None
    role: str
    is_active: bool
    email_verified: bool
    created_at: str | None = None
    last_login_at: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class MessageOut(BaseModel):
    message: str


class FolderOut(BaseModel):
    key: str
    title: str
    folder_id: str | None = None
    url: str | None = None
    image_count: int = 0
    face_count: int = 0
    hidden: bool = False
    date_label: str | None = None
    created_at: str | None = None


class FolderCreateIn(BaseModel):
    url: str = Field(min_length=10, max_length=1000)
    hidden: bool = False
    include_subfolders: bool = True


class FolderListOut(BaseModel):
    items: list[FolderOut]
    total: int


class EventOut(BaseModel):
    id: str
    slug: str
    title: str
    description: str = ""
    folder_key: str
    drive_pending: bool = False
    owner_id: str | None = None
    cover_url: str | None = None
    drive_uploaded_at: str | None = None
    date_label: str | None = None
    image_count: int = 0
    face_count: int = 0
    attendee_count: int = 0
    reminder_count: int = 0
    is_attending: bool = False
    is_owner: bool = False
    is_public: bool = True
    created_at: str | None = None


class EventCreateIn(BaseModel):
    """Drive linki varsa taranır; yoksa etkinlik hatırlatma modunda açılır."""

    url: str | None = Field(default=None, max_length=1000)
    title: str | None = Field(default=None, max_length=160)
    description: str = Field(default="", max_length=2000)
    event_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    include_subfolders: bool = True


class EventDriveIn(BaseModel):
    url: str = Field(min_length=10, max_length=1000)
    include_subfolders: bool = True


class ReminderIn(BaseModel):
    email: EmailStr


class EventListOut(BaseModel):
    items: list[EventOut]
    total: int


class EventPhotoOut(BaseModel):
    file_id: str
    name: str
    thumb_url: str
    width: int = 0
    height: int = 0


class EventPhotoListOut(BaseModel):
    items: list[EventPhotoOut]
    total: int


class JobOut(BaseModel):
    id: str
    folder_key: str
    kind: str
    status: str
    progress: float
    processed: int
    total: int
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    result: dict[str, Any] | None = None


class JobListOut(BaseModel):
    items: list[JobOut]
    total: int


class SearchResultOut(BaseModel):
    file_id: str
    name: str
    path: str | None = None
    score: float
    width: int = 0
    height: int = 0
    thumb_url: str | None = None
    download_url: str | None = None
    drive_url: str | None = None
    drive_download_url: str | None = None


class SearchOut(BaseModel):
    folder_key: str
    count: int
    results: list[SearchResultOut]
    took_ms: float
    query_embedding: list[float] = Field(default_factory=list)


class EmbedOut(BaseModel):
    """Yalnızca yüz vektörü. D1 okuma/yazma içermez (source of truth korunur)."""

    embedding: list[float] = Field(default_factory=list)
    ok: bool = False


class PreviewZipIn(BaseModel):
    folder_key: str
    file_ids: list[_FileId] = Field(default_factory=list, max_length=500)


class BulkDownloadIn(BaseModel):
    file_ids: list[_FileId] = Field(default_factory=list, max_length=200)
    size: int = Field(default=720, ge=320, le=2048)
