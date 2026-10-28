from __future__ import annotations

import math
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

from .timezone import now_in_beijing

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


def _resolve_db_path() -> Path:
    configured_path = os.getenv("TODO_DB_PATH", "").strip()
    if not configured_path:
        return DATA_DIR / "reminder.db"
    db_path = Path(configured_path).expanduser()
    if not db_path.is_absolute():
        db_path = BASE_DIR.parent / db_path
    return db_path


DB_PATH = _resolve_db_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _env_float(name: str, default: float, *, minimum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    if not math.isfinite(value) or value < minimum:
        return default
    return value


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return value if value >= minimum else default


SQLITE_TIMEOUT_SECONDS = _env_float("TODO_SQLITE_TIMEOUT_SECONDS", 30.0, minimum=0.1)
SQLITE_BUSY_TIMEOUT_MS = _env_int("TODO_SQLITE_BUSY_TIMEOUT_MS", 30000, minimum=0)
NotificationType = Literal["start", "end", "daily"]
SCHEMA_VERSION = 2

TaskMutation = Callable[[Mapping[str, Any]], Tuple[Dict[str, Any], Sequence[NotificationType]]]

_TASK_UPDATE_COLUMNS = frozenset(
    {
        "title",
        "description",
        "start_at",
        "start_all_day",
        "end_at",
        "end_all_day",
        "start_notified",
        "end_notified",
        "daily_reminder",
        "last_daily_notified",
    }
)


def _connect() -> sqlite3.Connection:
    """Create a SQLite connection configured for mixed API/thread usage."""
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db() -> None:
    """Create or migrate the SQLite schema without losing existing data."""
    with closing(_connect()) as conn:
        current_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if current_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {current_version} is newer than this application supports ({SCHEMA_VERSION})"
            )

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                start_at TEXT NOT NULL,
                start_all_day INTEGER NOT NULL DEFAULT 0,
                end_at TEXT,
                end_all_day INTEGER NOT NULL DEFAULT 0,
                start_notified INTEGER NOT NULL DEFAULT 0,
                end_notified INTEGER NOT NULL DEFAULT 0,
                daily_reminder INTEGER NOT NULL DEFAULT 0,
                last_daily_notified TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                webhook_url TEXT DEFAULT '',
                deadline_notice_minutes INTEGER NOT NULL DEFAULT 30,
                daily_reminder_time TEXT NOT NULL DEFAULT '09:00'
            );

            CREATE TABLE IF NOT EXISTS reminder_claims (
                task_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                notification_key TEXT NOT NULL,
                claim_token TEXT NOT NULL DEFAULT '',
                claimed_at TEXT NOT NULL,
                claimed_until TEXT NOT NULL,
                PRIMARY KEY (task_id, notification_type, notification_key)
            );
            """
        )

        # Compatibility columns must be added before indexes or statements that
        # reference them. Older databases otherwise fail during application boot.
        _ensure_column(conn, "tasks", "daily_reminder", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "tasks", "last_daily_notified", "TEXT")
        _ensure_column(conn, "settings", "daily_reminder_time", "TEXT NOT NULL DEFAULT '09:00'")
        _ensure_column(conn, "reminder_claims", "claim_token", "TEXT NOT NULL DEFAULT ''")

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_start_at ON tasks(start_at);
            CREATE INDEX IF NOT EXISTS idx_tasks_end_at ON tasks(end_at);
            CREATE INDEX IF NOT EXISTS idx_tasks_daily_reminder ON tasks(daily_reminder, end_at);
            CREATE INDEX IF NOT EXISTS idx_reminder_claims_expiry ON reminder_claims(claimed_until);
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO settings (
                id, webhook_url, deadline_notice_minutes, daily_reminder_time
            ) VALUES (1, '', 30, '09:00')
            """
        )
        conn.execute(
            "UPDATE settings SET daily_reminder_time = COALESCE(NULLIF(daily_reminder_time, ''), '09:00') WHERE id = 1"
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _row_to_task(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "start_at": row["start_at"],
        "start_all_day": bool(row["start_all_day"]),
        "end_at": row["end_at"],
        "end_all_day": bool(row["end_all_day"]),
        "start_notified": bool(row["start_notified"]),
        "end_notified": bool(row["end_notified"]),
        "daily_reminder": bool(row["daily_reminder"]),
        "last_daily_notified": row["last_daily_notified"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _fetch_task(conn: sqlite3.Connection, task_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _row_to_task(row) if row else None


def list_tasks() -> List[Dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY start_at, COALESCE(end_at, start_at), id").fetchall()
    return [_row_to_task(row) for row in rows]


def list_tasks_for_reminders() -> List[Dict[str, Any]]:
    """Return only tasks that may still produce reminders."""
    # Task inputs are minute-precision. Keep a task eligible through the whole
    # configured end minute so a polling worker cannot miss a 17:00 reminder
    # merely because it wakes at 17:00:15.
    now_minute_iso = now_in_beijing().replace(second=0, microsecond=0).isoformat()
    with closing(_connect()) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE start_notified = 0
               OR (end_notified = 0 AND end_at IS NOT NULL)
               OR (daily_reminder = 1 AND (end_at IS NULL OR end_at >= ?))
            ORDER BY start_at, COALESCE(end_at, start_at), id
            """,
            (now_minute_iso,),
        ).fetchall()
    return [_row_to_task(row) for row in rows]


def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    with closing(_connect()) as conn:
        return _fetch_task(conn, task_id)


def create_task(data: Dict[str, Any]) -> Dict[str, Any]:
    unknown_columns = set(data) - _TASK_UPDATE_COLUMNS
    if unknown_columns:
        raise ValueError(f"Unsupported task fields: {', '.join(sorted(unknown_columns))}")

    now_iso = now_in_beijing().isoformat()
    payload = {
        **data,
        "start_notified": 0,
        "end_notified": 0,
        "daily_reminder": int(bool(data.get("daily_reminder", 0))),
        "last_daily_notified": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    columns = ", ".join(payload.keys())
    placeholders = ", ".join(["?"] * len(payload))
    values = list(payload.values())
    with closing(_connect()) as conn:
        cursor = conn.execute(f"INSERT INTO tasks ({columns}) VALUES ({placeholders})", values)
        task_id = cursor.lastrowid
        conn.commit()
        created = _fetch_task(conn, task_id)
    if created is None:
        raise RuntimeError(f"Failed to load created task {task_id}")
    return created


def mutate_task(task_id: int, mutation: TaskMutation) -> Optional[Dict[str, Any]]:
    """Read, derive and write a task under one SQLite write transaction.

    This is used by partial API updates so concurrent requests cannot merge
    against a stale snapshot and silently overwrite one another's changes.
    """
    with closing(_connect()) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = _fetch_task(conn, task_id)
            if existing is None:
                conn.commit()
                return None

            data, clear_claim_types = mutation(existing)
            unknown_columns = set(data) - _TASK_UPDATE_COLUMNS
            if unknown_columns:
                raise ValueError(f"Unsupported task fields: {', '.join(sorted(unknown_columns))}")

            payload = data.copy()
            payload["updated_at"] = now_in_beijing().isoformat()
            assignments = ", ".join(f"{key} = ?" for key in payload)
            values = [*payload.values(), task_id]
            conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", values)
            _clear_notification_claims(conn, task_id, clear_claim_types)
            updated = _fetch_task(conn, task_id)
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise


def update_task(
    task_id: int,
    data: Dict[str, Any],
    *,
    clear_claim_types: Sequence[NotificationType] = (),
) -> Optional[Dict[str, Any]]:
    unknown_columns = set(data) - _TASK_UPDATE_COLUMNS
    if unknown_columns:
        raise ValueError(f"Unsupported task fields: {', '.join(sorted(unknown_columns))}")

    payload = data.copy()
    payload["updated_at"] = now_in_beijing().isoformat()
    assignments = ", ".join(f"{key} = ?" for key in payload.keys())
    values = list(payload.values()) + [task_id]
    with closing(_connect()) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = _fetch_task(conn, task_id)
            if not existing:
                conn.commit()
                return None
            conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", values)
            _clear_notification_claims(conn, task_id, clear_claim_types)
            updated = _fetch_task(conn, task_id)
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise


def delete_task(task_id: int) -> bool:
    with closing(_connect()) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM reminder_claims WHERE task_id = ?", (task_id,))
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount == 1
        except Exception:
            conn.rollback()
            raise


def _clear_notification_claims(
    conn: sqlite3.Connection,
    task_id: int,
    notification_types: Sequence[NotificationType],
) -> None:
    if not notification_types:
        return
    placeholders = ", ".join("?" for _ in notification_types)
    conn.execute(
        f"DELETE FROM reminder_claims WHERE task_id = ? AND notification_type IN ({placeholders})",
        (task_id, *notification_types),
    )


def clear_notification_claims(task_id: int, notification_types: Sequence[NotificationType]) -> None:
    if not notification_types:
        return
    with closing(_connect()) as conn:
        _clear_notification_claims(conn, task_id, notification_types)
        conn.commit()


def daily_notification_key(task: Dict[str, Any], daily_date: str) -> str:
    """Build a daily claim key tied to the schedule snapshot being processed."""
    return "|".join(
        (
            "v2",
            daily_date,
            str(task.get("start_at") or ""),
            "1" if task.get("start_all_day") else "0",
            str(task.get("end_at") or ""),
            "1" if task.get("end_all_day") else "0",
        )
    )


def _daily_notification_is_pending(row: sqlite3.Row, notification_key: str) -> bool:
    daily_date = notification_key
    if notification_key.startswith("v2|"):
        parts = notification_key.split("|", 5)
        if len(parts) != 6:
            return False
        _, daily_date, start_at, start_all_day, end_at, end_all_day = parts
        if (
            row["start_at"] != start_at
            or bool(row["start_all_day"]) != (start_all_day == "1")
            or (row["end_at"] or "") != end_at
            or bool(row["end_all_day"]) != (end_all_day == "1")
        ):
            return False
    return bool(row["daily_reminder"]) and row["last_daily_notified"] != daily_date


def _notification_is_pending(
    conn: sqlite3.Connection,
    task_id: int,
    notification_type: NotificationType,
    notification_key: str,
) -> bool:
    row = conn.execute(
        """
        SELECT start_at, end_at, start_notified, end_notified,
               start_all_day, end_all_day, daily_reminder, last_daily_notified
        FROM tasks
        WHERE id = ?
        """,
        (task_id,),
    ).fetchone()
    if row is None:
        return False
    if notification_type == "start":
        return not row["start_notified"] and row["start_at"] == notification_key
    if notification_type == "end":
        return not row["end_notified"] and row["end_at"] is not None and row["end_at"] == notification_key
    if notification_type == "daily":
        return _daily_notification_is_pending(row, notification_key)
    raise ValueError(f"Unsupported notification type: {notification_type}")


def claim_notification_with_token(
    task_id: int,
    notification_type: NotificationType,
    notification_key: str,
    ttl_seconds: int,
) -> Optional[str]:
    """Atomically claim a current reminder slot and return its owner token."""
    ttl_seconds = max(1, int(ttl_seconds))
    now = now_in_beijing()
    claim_until = now + timedelta(seconds=ttl_seconds)
    claim_token = uuid.uuid4().hex
    with closing(_connect()) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM reminder_claims WHERE claimed_until <= ?", (now.isoformat(),))
            if not _notification_is_pending(conn, task_id, notification_type, notification_key):
                conn.commit()
                return None
            cursor = conn.execute(
                """
                INSERT INTO reminder_claims (
                    task_id,
                    notification_type,
                    notification_key,
                    claim_token,
                    claimed_at,
                    claimed_until
                )
                SELECT ?, ?, ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM reminder_claims
                    WHERE task_id = ?
                      AND notification_type = ?
                      AND notification_key = ?
                      AND claimed_until > ?
                )
                """,
                (
                    task_id,
                    notification_type,
                    notification_key,
                    claim_token,
                    now.isoformat(),
                    claim_until.isoformat(),
                    task_id,
                    notification_type,
                    notification_key,
                    now.isoformat(),
                ),
            )
            conn.commit()
            return claim_token if cursor.rowcount == 1 else None
        except Exception:
            conn.rollback()
            raise


def claim_notification(task_id: int, notification_type: NotificationType, notification_key: str, ttl_seconds: int) -> bool:
    """Backward-compatible boolean wrapper around tokenized reminder claims."""
    return claim_notification_with_token(task_id, notification_type, notification_key, ttl_seconds) is not None


def release_notification_claim(
    task_id: int,
    notification_type: NotificationType,
    notification_key: str,
    claim_token: Optional[str] = None,
) -> None:
    with closing(_connect()) as conn:
        if claim_token:
            conn.execute(
                """
                DELETE FROM reminder_claims
                WHERE task_id = ? AND notification_type = ?
                  AND notification_key = ? AND claim_token = ?
                """,
                (task_id, notification_type, notification_key, claim_token),
            )
        else:
            conn.execute(
                "DELETE FROM reminder_claims WHERE task_id = ? AND notification_type = ? AND notification_key = ?",
                (task_id, notification_type, notification_key),
            )
        conn.commit()


def complete_notification(
    task_id: int,
    notification_type: NotificationType,
    notification_key: str,
    *,
    daily_date: Optional[str] = None,
    claim_token: Optional[str] = None,
) -> bool:
    """Persist a successful send and clear its temporary claim atomically."""
    now_iso = now_in_beijing().isoformat()
    with closing(_connect()) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            claim_query = (
                "SELECT 1 FROM reminder_claims "
                "WHERE task_id = ? AND notification_type = ? AND notification_key = ?"
            )
            claim_params: tuple[Any, ...] = (task_id, notification_type, notification_key)
            if claim_token:
                claim_query += " AND claim_token = ?"
                claim_params += (claim_token,)
            if conn.execute(claim_query, claim_params).fetchone() is None:
                conn.commit()
                return False

            if notification_type == "start":
                cursor = conn.execute(
                    "UPDATE tasks SET start_notified = 1, updated_at = ? "
                    "WHERE id = ? AND start_notified = 0 AND start_at = ?",
                    (now_iso, task_id, notification_key),
                )
            elif notification_type == "end":
                cursor = conn.execute(
                    "UPDATE tasks SET end_notified = 1, updated_at = ? "
                    "WHERE id = ? AND end_notified = 0 AND end_at = ?",
                    (now_iso, task_id, notification_key),
                )
            elif notification_type == "daily":
                if daily_date is None:
                    raise ValueError("daily_date is required for daily notification completion")
                cursor = conn.execute(
                    "UPDATE tasks SET last_daily_notified = ?, updated_at = ? "
                    "WHERE id = ? AND daily_reminder = 1 "
                    "AND (last_daily_notified IS NULL OR last_daily_notified != ?)",
                    (daily_date, now_iso, task_id, daily_date),
                )
            else:
                raise ValueError(f"Unsupported notification type: {notification_type}")

            if claim_token:
                conn.execute(
                    "DELETE FROM reminder_claims WHERE task_id = ? AND notification_type = ? "
                    "AND notification_key = ? AND claim_token = ?",
                    (task_id, notification_type, notification_key, claim_token),
                )
            else:
                conn.execute(
                    "DELETE FROM reminder_claims WHERE task_id = ? AND notification_type = ? AND notification_key = ?",
                    (task_id, notification_type, notification_key),
                )
            conn.commit()
            return cursor.rowcount == 1
        except Exception:
            conn.rollback()
            raise


def get_settings() -> Dict[str, Any]:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        if not row:
            conn.execute(
                """
                INSERT OR IGNORE INTO settings (
                    id, webhook_url, deadline_notice_minutes, daily_reminder_time
                ) VALUES (1, '', 30, '09:00')
                """
            )
            conn.commit()
            row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if row is None:
        raise RuntimeError("settings row missing after recovery")
    return {
        "webhook_url": row["webhook_url"] or "",
        "deadline_notice_minutes": row["deadline_notice_minutes"],
        "daily_reminder_time": row["daily_reminder_time"] or "09:00",
    }


def update_settings(webhook_url: str, deadline_notice_minutes: int, daily_reminder_time: str) -> Dict[str, Any]:
    with closing(_connect()) as conn:
        conn.execute(
            """
            INSERT INTO settings (id, webhook_url, deadline_notice_minutes, daily_reminder_time)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                webhook_url = excluded.webhook_url,
                deadline_notice_minutes = excluded.deadline_notice_minutes,
                daily_reminder_time = excluded.daily_reminder_time
            """,
            (webhook_url, deadline_notice_minutes, daily_reminder_time),
        )
        conn.commit()
    return get_settings()
