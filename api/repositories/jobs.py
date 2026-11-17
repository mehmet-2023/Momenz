from __future__ import annotations

from typing import Any

from ..db import D1Client
from .common import dumps, loads, sql_now

_JOB_COLUMNS = """
    id, owner_id, folder_key, kind, status, payload, progress, processed,
    total, result, error, worker_id, claimed_at, heartbeat_at,
    created_at, updated_at
"""


def _shape(row: dict) -> dict:
    return {
        "id": str(row.get("id") or ""),
        "owner_id": str(row.get("owner_id") or ""),
        "folder_key": str(row.get("folder_key") or ""),
        "kind": str(row.get("kind") or "index"),
        "status": str(row.get("status") or "queued"),
        "payload": loads(row.get("payload"), {}) or {},
        "progress": float(row.get("progress") or 0.0),
        "processed": int(row.get("processed") or 0),
        "total": int(row.get("total") or 0),
        "result": loads(row.get("result"), None),
        "error": row.get("error"),
        "worker_id": row.get("worker_id"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def create(
    db: D1Client,
    *,
    job_id: str,
    owner_id: str,
    folder_key: str,
    kind: str = "index",
    payload: dict[str, Any] | None = None,
) -> dict:
    db.execute(
        """
        INSERT INTO jobs
            (id, owner_id, folder_key, kind, status, payload, progress,
             processed, total, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'queued', ?, 0, 0, 0, ?, ?)
        """,
        (job_id, owner_id, folder_key, kind, dumps(payload), sql_now(), sql_now()),
    )
    return get(db, job_id) or {}


def get(db: D1Client, job_id: str) -> dict | None:
    row = db.query_one(
        f"SELECT {_JOB_COLUMNS} FROM jobs WHERE id = ? LIMIT 1", (job_id,)
    )
    return _shape(row) if row else None


def get_for_user(db: D1Client, owner_id: str, job_id: str) -> dict | None:
    row = db.query_one(
        f"SELECT {_JOB_COLUMNS} FROM jobs WHERE id = ? AND owner_id = ? LIMIT 1",
        (job_id, owner_id),
    )
    return _shape(row) if row else None


def list_for_user(
    db: D1Client, owner_id: str, limit: int = 50, folder_key: str | None = None
) -> list[dict]:
    sql = f"SELECT {_JOB_COLUMNS} FROM jobs WHERE owner_id = ?"
    params: list[Any] = [owner_id]
    if folder_key:
        sql += " AND folder_key = ?"
        params.append(folder_key)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(min(max(1, limit), 200))
    return [_shape(row) for row in db.query(sql, params)]


def claim_by_id(db: D1Client, job_id: str, worker_id: str) -> dict | None:
    rows = db.query(
        """
        UPDATE jobs
        SET status = 'running', worker_id = ?, claimed_at = ?,
            heartbeat_at = ?, updated_at = ?
        WHERE id = ? AND status = 'queued'
        RETURNING
            id, owner_id, folder_key, kind, status, payload, progress,
            processed, total, result, error, worker_id, created_at, updated_at
        """,
        (worker_id, sql_now(), sql_now(), sql_now(), job_id),
    )
    return _shape(rows[0]) if rows else None


def claim_next(db: D1Client, worker_id: str, kinds: list[str] | None = None) -> dict | None:
    sql = "SELECT id FROM jobs WHERE status = 'queued'"
    params: list[Any] = []
    if kinds:
        placeholders = ",".join("?" for _ in kinds)
        sql += f" AND kind IN ({placeholders})"
        params.extend(kinds)
    sql += " ORDER BY created_at ASC LIMIT 1"
    row = db.query_one(sql, params)
    return claim_by_id(db, str(row["id"]), worker_id) if row else None


def heartbeat(db: D1Client, job_id: str, worker_id: str) -> None:
    db.execute(
        """
        UPDATE jobs SET heartbeat_at = ?, updated_at = ?
        WHERE id = ? AND status = 'running' AND worker_id = ?
        """,
        (sql_now(), sql_now(), job_id, worker_id),
    )


def update_progress(
    db: D1Client,
    job_id: str,
    worker_id: str,
    *,
    progress: float,
    processed: int,
    total: int,
) -> None:
    db.execute(
        """
        UPDATE jobs
        SET progress = ?, processed = ?, total = ?, heartbeat_at = ?,
            updated_at = ?
        WHERE id = ? AND status = 'running' AND worker_id = ?
        """,
        (float(progress), int(processed), int(total), sql_now(), sql_now(), job_id, worker_id),
    )


def finish(db: D1Client, job_id: str, worker_id: str, result: dict[str, Any]) -> None:
    db.execute(
        """
        UPDATE jobs
        SET status = 'done', progress = 1, result = ?, error = NULL,
            heartbeat_at = ?, updated_at = ?
        WHERE id = ? AND status = 'running' AND worker_id = ?
        """,
        (dumps(result), sql_now(), sql_now(), job_id, worker_id),
    )


def fail(db: D1Client, job_id: str, worker_id: str, error: str) -> None:
    db.execute(
        """
        UPDATE jobs SET status = 'failed', error = ?, heartbeat_at = ?,
                        updated_at = ?
        WHERE id = ? AND status = 'running' AND worker_id = ?
        """,
        (error[:2000], sql_now(), sql_now(), job_id, worker_id),
    )


def cancel(db: D1Client, owner_id: str, job_id: str) -> bool:
    changes = db.execute(
        """
        UPDATE jobs SET status = 'canceled', updated_at = ?
        WHERE id = ? AND owner_id = ? AND status IN ('queued','running')
        """,
        (sql_now(), job_id, owner_id),
    )
    return changes > 0


def recover_stale(db: D1Client, stale_minutes: int = 30) -> int:
    """Çöken worker'ların işlerini tekrar kuyruğa alır."""
    marker = f"-{max(1, int(stale_minutes))} minutes"
    return db.execute(
        """
        UPDATE jobs
        SET status = 'queued', worker_id = NULL, updated_at = ?
        WHERE status = 'running'
          AND (heartbeat_at IS NULL OR heartbeat_at < datetime('now', ?))
        """,
        (sql_now(), marker),
    )


def queued_count(db: D1Client) -> int:
    row = db.query_one("SELECT COUNT(*) AS total FROM jobs WHERE status = 'queued'")
    return int((row or {}).get("total") or 0)
