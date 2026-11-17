-- Momenz — topluluk/etkinlik katmanı
-- 0001 uygulandıktan SONRA çalıştır.

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL,
    folder_key TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    event_date TEXT,
    cover_file_id TEXT,
    is_public INTEGER NOT NULL DEFAULT 1,
    max_attendees INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS events_date_idx ON events (event_date DESC);
CREATE INDEX IF NOT EXISTS events_owner_idx ON events (owner_id);
CREATE INDEX IF NOT EXISTS events_folder_idx ON events (folder_key);

CREATE TABLE IF NOT EXISTS event_attendees (
    event_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, user_id)
);
CREATE INDEX IF NOT EXISTS event_attendees_user_idx ON event_attendees (user_id);

-- Mevcut klasörleri etkinliğe çevir (meta JSON alanlarından).
INSERT OR IGNORE INTO events
    (id, slug, owner_id, folder_key, title, description, location,
     event_date, is_public, created_at)
SELECT
    'evt-' || lower(hex(randomblob(8))),
    'etkinlik-' || lower(hex(randomblob(5))),
    d.owner_id,
    d.folder_key,
    COALESCE(json_extract(d.meta, '$.folder_title'), 'Etkinlik'),
    '',
    '',
    json_extract(d.meta, '$.folder_date'),
    1,
    CURRENT_TIMESTAMP
FROM drive_folders d
WHERE d.owner_id IS NOT NULL AND d.owner_id <> '';

INSERT OR IGNORE INTO momenz_migrations (name) VALUES ('0002_events.sql');
