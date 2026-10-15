from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  topic TEXT NOT NULL DEFAULT '自我',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                  role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                  content TEXT NOT NULL,
                  citations_json TEXT NOT NULL DEFAULT '[]',
                  provider TEXT NOT NULL DEFAULT 'local',
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  kind TEXT NOT NULL DEFAULT 'context',
                  content TEXT NOT NULL,
                  source_session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
                  active INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT '待行动',
                  due_date TEXT,
                  evidence TEXT NOT NULL DEFAULT '',
                  review_note TEXT NOT NULL DEFAULT '',
                  source_session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  changed_judgment TEXT NOT NULL DEFAULT '',
                  result TEXT NOT NULL DEFAULT '',
                  repeated_error TEXT NOT NULL DEFAULT '',
                  boundary TEXT NOT NULL DEFAULT '',
                  next_experiment TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id,id);
                CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON tasks(status,due_date);
                """
            )

    @staticmethod
    def record(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        item = dict(row)
        if "citations_json" in item:
            item["citations"] = json.loads(item.pop("citations_json"))
        if "active" in item:
            item["active"] = bool(item["active"])
        return item

    @classmethod
    def records(cls, rows: list[sqlite3.Row]) -> list[dict]:
        return [cls.record(row) for row in rows]
