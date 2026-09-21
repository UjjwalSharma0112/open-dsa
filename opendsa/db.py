"""SQLite storage: versioned schema, migrations, schema-level seed helpers.

Layers (guidelines.md §2.1):
- progress track  -> ``patterns`` + ``questions_seen`` (never touched by compaction)
- transcript log  -> ``transcript`` (append-only)
- bank/dedup meta -> ``bank``
- session bookkeeping -> ``sessions``

Schema is versioned from day one via ``PRAGMA user_version``. The single
source of truth for "what version is this DB" is that pragma.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2

_MIGRATIONS: dict[int, str] = {
    1: """
        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at   TEXT NOT NULL DEFAULT (datetime('now')),
            model        TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active','closed')),
            settings_json TEXT
        );

        CREATE TABLE IF NOT EXISTS bank (
            question_id TEXT PRIMARY KEY,
            pattern     TEXT NOT NULL,
            difficulty  TEXT NOT NULL CHECK (difficulty IN ('easy','medium','hard'))
        );

        CREATE TABLE IF NOT EXISTS transcript (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL REFERENCES sessions(id),
            ts              TEXT NOT NULL DEFAULT (datetime('now')),
            turn_type       TEXT NOT NULL CHECK (turn_type IN
                            ('question','user_answer','verdict','followup','link','skip','note')),
            pattern         TEXT,
            difficulty      TEXT,
            question_id     TEXT,
            verdict         TEXT CHECK (verdict IS NULL OR verdict IN
                            ('correct','partial','wrong','skip')),
            advanced_manually INTEGER NOT NULL DEFAULT 0
                            CHECK (advanced_manually IN (0,1)),
            mistake_note    TEXT,
            payload         TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_transcript_session ON transcript(session_id, ts);
        CREATE INDEX IF NOT EXISTS idx_transcript_verdict ON transcript(verdict);

        CREATE TABLE IF NOT EXISTS patterns (
            pattern       TEXT PRIMARY KEY,
            position      INTEGER NOT NULL,
            status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','mastered')),
            difficulty    TEXT NOT NULL DEFAULT 'medium'
                          CHECK (difficulty IN ('easy','medium','hard')),
            attempts      INTEGER NOT NULL DEFAULT 0,
            correct_streak INTEGER NOT NULL DEFAULT 0,
            wrong_streak  INTEGER NOT NULL DEFAULT 0,
            mastered_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS questions_seen (
            pattern     TEXT NOT NULL REFERENCES patterns(pattern),
            question_id TEXT NOT NULL,
            PRIMARY KEY (pattern, question_id)
        );
    """,
    2: """
        ALTER TABLE sessions ADD COLUMN compacted_summary TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE transcript ADD COLUMN summarized INTEGER NOT NULL DEFAULT 0
            CHECK (summarized IN (0,1));
    """,
}


def connect(database_path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite DB and migrate it to SCHEMA_VERSION.

    check_same_thread=False lets the TUI thread and the controller thread share
    the connection; short transactions plus a busy timeout keep them safe.
    """
    path = Path(database_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    apply_migrations(conn)
    return conn


def apply_migrations(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version in range(current + 1, SCHEMA_VERSION + 1):
        script = _MIGRATIONS.get(version)
        if script is None:
            raise RuntimeError(
                f"DB at schema {current} but no migration path to {version}"
            )
        with conn:
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {version}")
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"DB schema {current} is newer than this app supports ({SCHEMA_VERSION})"
        )


def seed_patterns(conn: sqlite3.Connection, curriculum: Sequence[str]) -> None:
    """Insert the ordered curriculum into ``patterns`` (idempotent)."""
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO patterns (pattern, position) VALUES (?, ?)",
            [(name, pos) for pos, name in enumerate(curriculum)],
        )


def seed_bank(conn: sqlite3.Connection, bank_rows: Sequence[dict[str, Any]]) -> None:
    """Insert local metadata bank rows (idempotent). Each row: question_id, pattern, difficulty."""
    cleaned: list[tuple[str, str, str]] = []
    for row in bank_rows:
        question_id = str(row["question_id"])
        pattern = str(row["pattern"])
        difficulty = str(row["difficulty"]).lower()
        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError(f"bad difficulty {difficulty!r} for {question_id}")
        cleaned.append((question_id, pattern, difficulty))
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO bank (question_id, pattern, difficulty) VALUES (?, ?, ?)",
            cleaned,
        )


def load_bank_from_file(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).expanduser().open(encoding="utf-8") as fh:
        return json.load(fh)