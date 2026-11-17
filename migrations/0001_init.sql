-- Momenz API — D1 şeması (tek seferlik, idempotent çalıştırıcı ile)
-- Mevcut drive_face_index / drive_folders / drive_indexed_folders tabloları
-- korunur; yalnızca auth, multi-tenancy ve job kuyruğu eklenir.

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
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS refresh_tokens_user_idx ON refresh_tokens (user_id);

CREATE TABLE IF NOT EXISTS verification_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS verification_tokens_user_idx ON verification_tokens (user_id);

-- Mevcut klasörleri bir kullanıcıya bağlamak için owner_id eklenir.
-- (mysql tarzı IF NOT EXISTS yoktur; migrate.py bu ALTER'ı güvenle atlar.)
ALTER TABLE drive_folders ADD COLUMN owner_id TEXT;
CREATE INDEX IF NOT EXISTS drive_folders_owner_idx ON drive_folders (owner_id);

CREATE TABLE IF NOT EXISTS folder_index_versions (
    folder_key TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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
);
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs (status, created_at);
CREATE INDEX IF NOT EXISTS jobs_owner_idx ON jobs (owner_id, created_at);

CREATE TABLE IF NOT EXISTS momenz_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
