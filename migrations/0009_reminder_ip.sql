-- Aynı IP'den hatırlatma bırakan ziyaretçi sayfayı yenilediğinde
-- "EMAILİNİ ALDIK" durumunu görebilmek için IP, jwt_secret ile harmanlanıp
-- sha256 olarak saklanır; ham IP veritabanına yazılmaz.
ALTER TABLE event_reminders ADD COLUMN ip_hash TEXT;
CREATE INDEX IF NOT EXISTS event_reminders_ip_idx ON event_reminders (event_id, ip_hash);
