import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from aiogram.types import User as TgUser

from .config import settings

log = logging.getLogger(__name__)

_conn: sqlite3.Connection | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id     INTEGER PRIMARY KEY,
    username        TEXT,
    first_name      TEXT,
    last_name       TEXT,
    language_code   TEXT,
    is_premium      INTEGER DEFAULT 0,
    started_at      TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    is_blocked      INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_users_started_at ON users(started_at);

CREATE TABLE IF NOT EXISTS broadcast_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id        INTEGER NOT NULL,
    payload_json    TEXT NOT NULL,
    audience        TEXT NOT NULL,
    progress_cursor INTEGER NOT NULL DEFAULT 0,
    total           INTEGER NOT NULL DEFAULT 0,
    sent            INTEGER NOT NULL DEFAULT 0,
    blocked         INTEGER NOT NULL DEFAULT 0,
    failed          INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_broadcast_status ON broadcast_jobs(status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _cursor() -> Iterator[sqlite3.Cursor]:
    assert _conn is not None, "db.init() not called"
    cur = _conn.cursor()
    try:
        yield cur
        _conn.commit()
    finally:
        cur.close()


def init() -> None:
    global _conn
    if _conn is not None:
        return
    path = Path(settings.db_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(path), check_same_thread=False)
    # WAL + NORMAL keeps per-send cursor writes cheap during broadcasts.
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA synchronous=NORMAL")
    _conn.executescript(_SCHEMA)
    _conn.commit()
    log.info("[db] opened %s", path)


def close() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


# ──────────────────────────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────────────────────────

def upsert_user(user: TgUser) -> bool:
    """
    Record or refresh a user. Returns True if this was a first-time /start,
    False if the user already existed.
    """
    now = _now()
    with _cursor() as cur:
        cur.execute(
            "SELECT telegram_id FROM users WHERE telegram_id = ?",
            (user.id,),
        )
        existed = cur.fetchone() is not None

        if existed:
            cur.execute(
                """
                UPDATE users
                   SET username = ?, first_name = ?, last_name = ?,
                       language_code = ?, is_premium = ?, last_seen_at = ?
                 WHERE telegram_id = ?
                """,
                (
                    user.username,
                    user.first_name,
                    user.last_name,
                    user.language_code,
                    1 if user.is_premium else 0,
                    now,
                    user.id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, last_name,
                                   language_code, is_premium, started_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.username,
                    user.first_name,
                    user.last_name,
                    user.language_code,
                    1 if user.is_premium else 0,
                    now,
                    now,
                ),
            )
    return not existed


def total_users() -> int:
    with _cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users")
        return int(cur.fetchone()[0])


def blocked_count() -> int:
    with _cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
        return int(cur.fetchone()[0])


def recent_users(limit: int = 20, offset: int = 0) -> list[dict]:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT telegram_id, username, first_name, last_name,
                   started_at, last_seen_at, is_blocked
              FROM users
             ORDER BY started_at DESC
             LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def mark_blocked(telegram_id: int) -> None:
    with _cursor() as cur:
        cur.execute(
            "UPDATE users SET is_blocked = 1 WHERE telegram_id = ?",
            (telegram_id,),
        )


def unblock_user(telegram_id: int) -> bool:
    """
    Flip is_blocked back to 0 if — and only if — the user was blocked.
    Returns True if an unblock actually happened. No-op (and one
    indexed UPDATE that touches zero rows) if the user wasn't blocked.
    """
    with _cursor() as cur:
        cur.execute(
            "UPDATE users SET is_blocked = 0 WHERE telegram_id = ? AND is_blocked = 1",
            (telegram_id,),
        )
        return cur.rowcount > 0


# ──────────────────────────────────────────────────────────────────
# Broadcasts
# ──────────────────────────────────────────────────────────────────

def count_audience(audience: str) -> int:
    with _cursor() as cur:
        if audience == "all":
            cur.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 0")
        elif audience in ("active_7d", "active_30d"):
            days = 7 if audience == "active_7d" else 30
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            cur.execute(
                "SELECT COUNT(*) FROM users WHERE is_blocked = 0 AND last_seen_at >= ?",
                (cutoff,),
            )
        else:
            return 0
        return int(cur.fetchone()[0])


def create_broadcast_job(
    admin_id: int, payload: dict, audience: str, total: int
) -> int:
    now = _now()
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO broadcast_jobs
                (admin_id, payload_json, audience, progress_cursor,
                 total, sent, blocked, failed, status, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, 0, 0, 0, 'running', ?, ?)
            """,
            (admin_id, json.dumps(payload), audience, total, now, now),
        )
        return int(cur.lastrowid)


def update_broadcast_progress(
    job_id: int, cursor: int, sent: int, blocked: int, failed: int
) -> None:
    with _cursor() as cur:
        cur.execute(
            """
            UPDATE broadcast_jobs
               SET progress_cursor = ?, sent = ?, blocked = ?, failed = ?,
                   updated_at = ?
             WHERE id = ?
            """,
            (cursor, sent, blocked, failed, _now(), job_id),
        )


def finish_broadcast_job(job_id: int, status: str = "done") -> None:
    with _cursor() as cur:
        cur.execute(
            "UPDATE broadcast_jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), job_id),
        )


def get_running_jobs() -> list[dict]:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT id, admin_id, payload_json, audience, progress_cursor,
                   total, sent, blocked, failed, status, created_at, updated_at
              FROM broadcast_jobs
             WHERE status = 'running'
             ORDER BY id
            """
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_broadcast_batch(audience: str, after_id: int, limit: int = 20) -> list[dict]:
    """Next batch of users (telegram_id > after_id) matching the audience filter."""
    with _cursor() as cur:
        if audience == "all":
            cur.execute(
                """
                SELECT telegram_id, username, first_name
                  FROM users
                 WHERE telegram_id > ? AND is_blocked = 0
                 ORDER BY telegram_id
                 LIMIT ?
                """,
                (after_id, limit),
            )
        elif audience in ("active_7d", "active_30d"):
            days = 7 if audience == "active_7d" else 30
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            cur.execute(
                """
                SELECT telegram_id, username, first_name
                  FROM users
                 WHERE telegram_id > ? AND is_blocked = 0 AND last_seen_at >= ?
                 ORDER BY telegram_id
                 LIMIT ?
                """,
                (after_id, cutoff, limit),
            )
        else:
            return []
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]