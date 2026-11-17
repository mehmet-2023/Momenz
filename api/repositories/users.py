from __future__ import annotations

from datetime import datetime
from typing import Any

from ..db import D1Client
from .common import sql_after, sql_now

_USER_COLUMNS = """
    id, email, name, role, is_active, email_verified, password_hash,
    created_at, last_login_at
"""


def get_by_email(db: D1Client, email: str) -> dict | None:
    return db.query_one(
        f"SELECT {_USER_COLUMNS} FROM users WHERE email = ? COLLATE NOCASE LIMIT 1",
        (email,),
    )


def get_by_id(db: D1Client, user_id: str) -> dict | None:
    return db.query_one(
        f"SELECT {_USER_COLUMNS} FROM users WHERE id = ? LIMIT 1", (user_id,)
    )


def create_user(
    db: D1Client,
    *,
    user_id: str,
    email: str,
    name: str | None,
    password_hash: str,
    email_verified: bool = False,
    role: str = "user",
) -> None:
    db.execute(
        """
        INSERT INTO users
            (id, email, name, role, is_active, email_verified, password_hash,
             created_at)
        VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            user_id,
            email.strip().lower(),
            name or None,
            role,
            1 if email_verified else 0,
            password_hash,
            sql_now(),
        ),
    )


def update_last_login(db: D1Client, user_id: str) -> None:
    db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (sql_now(), user_id))


def set_password(db: D1Client, user_id: str, password_hash: str) -> None:
    db.execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (password_hash, sql_now(), user_id),
    )


def set_email_verified(db: D1Client, user_id: str) -> None:
    db.execute(
        "UPDATE users SET email_verified = 1, updated_at = ? WHERE id = ?",
        (sql_now(), user_id),
    )


def list_users(db: D1Client, limit: int = 50, offset: int = 0) -> list[dict]:
    return db.query(
        """
        SELECT id, email, name, role, is_active, email_verified, created_at,
               last_login_at
        FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?
        """,
        (min(max(1, limit), 200), max(0, offset)),
    )


# ------------------------------------------------------------- refresh tokens
def store_refresh_token(
    db: D1Client, token_id: str, user_id: str, fingerprint: str, expires_at: datetime
) -> None:
    db.execute(
        """
        INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            token_id,
            user_id,
            fingerprint,
            expires_at.strftime("%Y-%m-%d %H:%M:%S"),
            sql_now(),
        ),
    )


def get_refresh_token(db: D1Client, fingerprint: str) -> dict | None:
    return db.query_one(
        """
        SELECT id, user_id, expires_at, revoked_at
        FROM refresh_tokens
        WHERE token_hash = ? LIMIT 1
        """,
        (fingerprint,),
    )


def revoke_refresh_token(db: D1Client, fingerprint: str) -> None:
    db.execute(
        "UPDATE refresh_tokens SET revoked_at = ? WHERE token_hash = ?",
        (sql_now(), fingerprint),
    )


def revoke_all_for_user(db: D1Client, user_id: str) -> None:
    db.execute(
        "UPDATE refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
        (sql_now(), user_id),
    )


def purge_expired(db: D1Client) -> int:
    removed = db.execute("DELETE FROM refresh_tokens WHERE expires_at < datetime('now')")
    db.execute("DELETE FROM verification_tokens WHERE expires_at < datetime('now')")
    return removed


# ---------------------------------------------------------- verification tokens
def create_verification_token(
    db: D1Client, token_id: str, user_id: str, kind: str, fingerprint: str, ttl_hours: int
) -> None:
    db.execute(
        """
        INSERT INTO verification_tokens
            (id, user_id, kind, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (token_id, user_id, kind, fingerprint, sql_after(ttl_hours * 3600), sql_now()),
    )


def consume_verification_token(
    db: D1Client, fingerprint: str, kind: str
) -> dict | None:
    row = db.query_one(
        """
        SELECT id, user_id, kind FROM verification_tokens
        WHERE token_hash = ? AND kind = ? AND used_at IS NULL
          AND expires_at > datetime('now')
        LIMIT 1
        """,
        (fingerprint, kind),
    )
    if not row:
        return None
    db.execute(
        "UPDATE verification_tokens SET used_at = ? WHERE id = ?",
        (sql_now(), row["id"]),
    )
    return row


def count_users(db: D1Client) -> int:
    row = db.query_one("SELECT COUNT(*) AS total FROM users")
    return int((row or {}).get("total") or 0)
