"""Idempotent, self-healing database schema bootstrap.

``migrations/*.sql`` are intentionally excluded from the production Docker
image (they are ops-only artifacts).  The running API therefore needs to carry
the schema it depends on so a fresh or partially migrated database repairs
itself on every startup.  This is the single source of truth for the tables and
indexes the FastAPI service reads/writes.

Everything here is ``CREATE ... IF NOT EXISTS``: existing rows, versions and
flags are never touched.  ``drive_face_index`` is deliberately absent (it was
dissolved into ``folder_matrices.files``).
"""

from __future__ import annotations

from .turso import TursoClient

# Her girdi tek bir SQL ifadesidir; db.batch() ile tek istekte çalıştırılır.
_STATEMENTS: tuple[str, ...] = (
    # --- legacy/klasör katmanı (mevcut veri korunur) -------------------------
    """
    CREATE TABLE IF NOT EXISTS drive_folders (
        folder_key TEXT NOT NULL PRIMARY KEY,
        meta TEXT NOT NULL DEFAULT '{}',
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        owner_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS drive_indexed_folders (
        folder_id TEXT NOT NULL PRIMARY KEY,
        root_key TEXT NOT NULL,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS drive_folders_owner_idx ON drive_folders (owner_id)",
    "CREATE INDEX IF NOT EXISTS drive_indexed_folders_root_idx ON drive_indexed_folders (root_key)",
    # --- auth / kullanıcı ----------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name TEXT,
        role TEXT NOT NULL DEFAULT 'user',
        is_active INTEGER NOT NULL DEFAULT 1,
        email_verified INTEGER NOT NULL DEFAULT 0,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT,
        last_login_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS refresh_tokens (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS refresh_tokens_user_idx ON refresh_tokens (user_id)",
    """
    CREATE TABLE IF NOT EXISTS verification_tokens (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL,
        used_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS verification_tokens_user_idx ON verification_tokens (user_id)",
    # --- job kuyruğu ---------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        folder_key TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'index',
        status TEXT NOT NULL DEFAULT 'queued',
        payload TEXT NOT NULL DEFAULT '{}',
        progress REAL NOT NULL DEFAULT 0,
        processed INTEGER NOT NULL DEFAULT 0,
        total INTEGER NOT NULL DEFAULT 0,
        result TEXT,
        error TEXT,
        worker_id TEXT,
        claimed_at TEXT,
        heartbeat_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs (status, created_at)",
    "CREATE INDEX IF NOT EXISTS jobs_owner_idx ON jobs (owner_id, created_at)",
    # --- etkinlikler ---------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        slug TEXT NOT NULL UNIQUE,
        owner_id TEXT NOT NULL,
        folder_key TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        event_date TEXT,
        cover_file_id TEXT,
        is_public INTEGER NOT NULL DEFAULT 1,
        max_attendees INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS events_date_idx ON events (event_date DESC)",
    "CREATE INDEX IF NOT EXISTS events_owner_idx ON events (owner_id)",
    "CREATE INDEX IF NOT EXISTS events_folder_idx ON events (folder_key)",
    """
    CREATE TABLE IF NOT EXISTS event_attendees (
        event_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (event_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS event_attendees_user_idx ON event_attendees (user_id)",
    """
    CREATE TABLE IF NOT EXISTS event_reminders (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        email TEXT NOT NULL COLLATE NOCASE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        notified_at TEXT,
        UNIQUE (event_id, email)
    )
    """,
    "CREATE INDEX IF NOT EXISTS event_reminders_pending_idx ON event_reminders (event_id, notified_at)",
    # --- tek satırlık index --------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS folder_index_versions (
        folder_key TEXT PRIMARY KEY,
        version INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS folder_matrices (
        folder_key TEXT PRIMARY KEY,
        version INTEGER NOT NULL DEFAULT 0,
        is_public INTEGER NOT NULL DEFAULT 0,
        matrix BLOB NOT NULL,
        metas BLOB NOT NULL,
        rows INTEGER NOT NULL DEFAULT 0,
        files BLOB,
        images INTEGER NOT NULL DEFAULT 0,
        done INTEGER NOT NULL DEFAULT 0,
        no_face INTEGER NOT NULL DEFAULT 0,
        errors INTEGER NOT NULL DEFAULT 0,
        first_file_id TEXT,
        cover_file_id TEXT,
        meta TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS momenz_migrations (
        name TEXT PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
)


# Eski kurulumlarda eksik kalan sütunlar. CREATE TABLE IF NOT EXISTS mevcut
# tabloyu değiştirmediği için bunlar ayrı ve hata toleranslı çalıştırılır.
_COLUMN_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE folder_matrices ADD COLUMN cover_file_id TEXT",
)


def ensure_schema(db: TursoClient) -> None:
    """Eksik tablo/index'leri idempotent olarak oluşturur; veriye dokunmaz."""
    db.batch([{"sql": statement} for statement in _STATEMENTS])
    # CREATE TABLE IF NOT EXISTS eski tabloya yeni sütun eklemez. Bu ifadeler
    # ayrı çalışır; sütun zaten varsa "duplicate column name" yok sayılır.
    for statement in _COLUMN_STATEMENTS:
        try:
            db.execute(statement)
        except Exception as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
