"""
SQLite-backed persistence layer.
Stores sessions, messages, execution plans, and artifact metadata.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from utils.logger import get_logger

logger = get_logger("storage.database", "db")

DB_PATH = os.getenv("DB_PATH", "storage/autoagent.db")


# ─────────────────────────────────────────────
# Schema DDL
# ─────────────────────────────────────────────

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    mode        TEXT DEFAULT 'safe',
    context     TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    attachments TEXT DEFAULT '[]',
    timestamp   TEXT NOT NULL,
    plan_id     TEXT,
    metadata    TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS plans (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    request_id      TEXT,
    intent_summary  TEXT,
    status          TEXT DEFAULT 'pending',
    steps_json      TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    name        TEXT NOT NULL,
    path        TEXT NOT NULL,
    type        TEXT NOT NULL,
    size_bytes  INTEGER,
    created_at  TEXT NOT NULL,
    description TEXT,
    step_id     TEXT
);

CREATE TABLE IF NOT EXISTS task_runs (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    plan_id     TEXT,
    status      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    error       TEXT,
    log_json    TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_plans_session ON plans(session_id);
"""


# ─────────────────────────────────────────────
# Database Manager
# ─────────────────────────────────────────────

class DatabaseManager:
    """Thread-safe SQLite wrapper."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(CREATE_TABLES)
        logger.info(f"Database ready: {self.db_path}")

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Sessions ──────────────────────────────

    def create_session(self, session_id: str, name: str = "New Session",
                       mode: str = "safe") -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions (id, name, created_at, updated_at, mode) VALUES (?,?,?,?,?)",
                (session_id, name, now, now, mode),
            )
        return {"id": session_id, "name": name, "created_at": now, "mode": mode}

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_session(self, session_id: str, **kwargs):
        kwargs["updated_at"] = datetime.utcnow().isoformat()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [session_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE sessions SET {sets} WHERE id = ?", values)

    def delete_session(self, session_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM plans WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM artifacts WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    # ── Messages ──────────────────────────────

    def save_message(self, msg_id: str, session_id: str, role: str,
                     content: str, attachments: List[str] = None,
                     plan_id: str = None, metadata: Dict = None):
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO messages
                   (id, session_id, role, content, attachments, timestamp, plan_id, metadata)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (msg_id, session_id, role, content,
                 json.dumps(attachments or []), now,
                 plan_id, json.dumps(metadata or {})),
            )

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["attachments"] = json.loads(d.get("attachments", "[]"))
                d["metadata"] = json.loads(d.get("metadata", "{}"))
                result.append(d)
            return result

    # ── Plans ─────────────────────────────────

    def save_plan(self, plan_id: str, session_id: str, request_id: str,
                  intent_summary: str, steps_data: Any):
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO plans
                   (id, session_id, request_id, intent_summary, steps_json, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (plan_id, session_id, request_id, intent_summary,
                 json.dumps(steps_data, default=str), now),
            )

    def get_plans(self, session_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM plans WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Artifacts ─────────────────────────────

    def save_artifact(self, artifact_id: str, session_id: str, name: str,
                      path: str, artifact_type: str, size_bytes: int = 0,
                      description: str = "", step_id: str = None):
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO artifacts
                   (id, session_id, name, path, type, size_bytes, created_at, description, step_id)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (artifact_id, session_id, name, path, artifact_type,
                 size_bytes, now, description, step_id),
            )

    def get_artifacts(self, session_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Task Runs ─────────────────────────────

    def create_task_run(self, run_id: str, session_id: str, plan_id: str = None):
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO task_runs (id, session_id, plan_id, status, started_at)
                   VALUES (?,?,?,?,?)""",
                (run_id, session_id, plan_id, "running", now),
            )

    def finish_task_run(self, run_id: str, status: str,
                        error: str = None, logs: List[str] = None):
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                """UPDATE task_runs
                   SET status=?, ended_at=?, error=?, log_json=?
                   WHERE id=?""",
                (status, now, error, json.dumps(logs or []), run_id),
            )

    def get_task_runs(self, session_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM task_runs WHERE session_id = ? ORDER BY started_at DESC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]


# Singleton
_db: Optional[DatabaseManager] = None


def get_db() -> DatabaseManager:
    global _db
    if _db is None:
        _db = DatabaseManager()
    return _db
