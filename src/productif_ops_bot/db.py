from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            telegram_user_id INTEGER UNIQUE,
            role TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            owner_id TEXT NOT NULL REFERENCES people(id),
            priority TEXT NOT NULL DEFAULT 'P1',
            status TEXT NOT NULL DEFAULT 'todo',
            due_date TEXT NOT NULL,
            sop_path TEXT,
            category TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            source_path TEXT NOT NULL DEFAULT '',
            proof_required INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            person_id TEXT NOT NULL REFERENCES people(id),
            status TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            proof TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS api_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL REFERENCES people(id),
            token_hash TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_used_at TEXT,
            revoked_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_api_tokens_person_id
        ON api_tokens(person_id);

        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL REFERENCES people(id),
            summary TEXT NOT NULL DEFAULT '',
            workspace_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    _add_missing_column(conn, "tasks", "category", "TEXT NOT NULL DEFAULT ''")
    _add_missing_column(conn, "tasks", "source", "TEXT NOT NULL DEFAULT ''")
    _add_missing_column(conn, "tasks", "source_path", "TEXT NOT NULL DEFAULT ''")
    _add_missing_column(conn, "checkins", "sync_run_id", "INTEGER REFERENCES sync_runs(id)")
    conn.commit()


def _add_missing_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
