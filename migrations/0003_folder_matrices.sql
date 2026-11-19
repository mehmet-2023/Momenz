-- Turso taşımasıyla birlikte arama matrisleri klasör başına tek BLOB satırında tutulur.
-- Böylece arama, 28.000+ yüz satırı yerine 1 satır okur.
CREATE TABLE IF NOT EXISTS folder_matrices (
  folder_key TEXT PRIMARY KEY,
  version INTEGER NOT NULL DEFAULT 0,
  is_public INTEGER NOT NULL DEFAULT 0,
  matrix BLOB NOT NULL,
  metas BLOB NOT NULL,
  rows INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
