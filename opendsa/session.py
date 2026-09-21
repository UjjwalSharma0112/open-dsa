"""Session start/resume. Resume last open session by default; --new is the
explicit fresh-start path (FR19 + guidelines 3).

Public helpers used by both the CLI (session.start) and the TUI screens
(seed / latest_active / open_new) so the UI can show a Resume/New prompt
before any session row is created.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import db
from .config import Config


def seed(conn: sqlite3.Connection, cfg: Config) -> None:
    """Idempotently seed the curriculum and the local bank."""
    db.seed_patterns(conn, list(cfg.curriculum))
    if cfg.bank.path and Path(cfg.bank.path).is_file():
        db.seed_bank(conn, db.load_bank_from_file(cfg.bank.path))


def latest_active(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT id FROM sessions WHERE status = 'active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def open_new(conn: sqlite3.Connection, model: str) -> int:
    with conn:
        cur = conn.execute("INSERT INTO sessions (model) VALUES (?)", (model,))
    return int(cur.lastrowid)


def start(cfg: Config, *, fresh: bool, model: str) -> tuple[sqlite3.Connection, int, bool]:
    """Return (connection, session_id, resumed)."""
    conn = db.connect(cfg.app.database_path)
    if fresh:
        seed(conn, cfg)
        return conn, open_new(conn, model), False

    existing = latest_active(conn)
    if existing is not None:
        return conn, existing, True

    seed(conn, cfg)
    return conn, open_new(conn, model), False


def last_question(conn: sqlite3.Connection, session_id: int) -> dict | None:
    """Latest non-summarized question of a session, for a resume screen."""
    row = conn.execute(
        "SELECT pattern, difficulty, question_id, payload FROM transcript "
        "WHERE session_id = ? AND turn_type = 'question' AND summarized = 0 "
        "ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return dict(row) if row else None