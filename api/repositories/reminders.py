from __future__ import annotations

from ..db import D1Client
from .common import sql_now


def add(
    db: D1Client,
    reminder_id: str,
    event_id: str,
    email: str,
    ip_hash: str | None = None,
) -> bool:
    """Aynı etkinlik + e-posta varsa yeni satır oluşturmaz."""
    changes = db.execute(
        """
        INSERT OR IGNORE INTO event_reminders (id, event_id, email, ip_hash)
        VALUES (?, ?, ?, ?)
        """,
        (reminder_id, event_id, email.strip().lower(), ip_hash or None),
    )
    return changes > 0


def has_ip(db: D1Client, event_id: str, ip_hash: str) -> bool:
    """Bu IP'den etkinliğe hatırlatma bırakılmış mı?"""
    if not ip_hash:
        return False
    row = db.query_one(
        """
        SELECT 1 FROM event_reminders
        WHERE event_id = ? AND ip_hash = ? LIMIT 1
        """,
        (event_id, ip_hash),
    )
    return row is not None


def pending_for_folder(db: D1Client, folder_key: str, limit: int = 1000) -> list[dict]:
    """Drive'ı bağlı etkinliklerde henüz bildirilmemiş hatırlatmalar."""
    return db.query(
        """
        SELECT r.id, r.email, e.id AS event_id, e.slug, e.title
        FROM event_reminders r
        JOIN events e ON e.id = r.event_id
        WHERE e.folder_key = ? AND r.notified_at IS NULL
        ORDER BY r.created_at ASC
        LIMIT ?
        """,
        (folder_key, max(1, min(int(limit), 5000))),
    )


def claim(db: D1Client, reminder_id: str) -> bool:
    """Aynı hatırlatmayı iki worker'ın aynı anda göndermesini engeller."""
    changes = db.execute(
        """
        UPDATE event_reminders SET notified_at = ?
        WHERE id = ? AND notified_at IS NULL
        """,
        (sql_now(), reminder_id),
    )
    return changes > 0


def release(db: D1Client, reminder_id: str) -> None:
    """Gönderim başarısız olduysa kaydı bir sonraki taramaya bırakır."""
    db.execute(
        "UPDATE event_reminders SET notified_at = NULL WHERE id = ?",
        (reminder_id,),
    )


def pending_count(db: D1Client, event_id: str) -> int:
    row = db.query_one(
        """
        SELECT COUNT(*) AS n FROM event_reminders
        WHERE event_id = ? AND notified_at IS NULL
        """,
        (event_id,),
    )
    return int((row or {}).get("n") or 0)


def total_count(db: D1Client, event_id: str) -> int:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM event_reminders WHERE event_id = ?",
        (event_id,),
    )
    return int((row or {}).get("n") or 0)
