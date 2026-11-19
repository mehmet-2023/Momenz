-- Drive'ı henüz yüklenmemiş etkinlikler için hatırlatma listesi.
-- Aynı e-posta aynı etkinliğe yalnızca bir kez eklenir.
CREATE TABLE IF NOT EXISTS event_reminders (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    email TEXT NOT NULL COLLATE NOCASE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notified_at TEXT,
    UNIQUE (event_id, email)
);
CREATE INDEX IF NOT EXISTS event_reminders_pending_idx
    ON event_reminders (event_id, notified_at);

INSERT OR IGNORE INTO momenz_migrations (name) VALUES ('0007_event_reminders.sql');
