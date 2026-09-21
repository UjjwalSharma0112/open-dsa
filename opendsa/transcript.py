"""Transcript log: append-only full history (guidelines 2.1). Never edited,
never summarized in place — compaction only marks rows ``summarized`` and moves
their gist into the session summary (NFR4: progress track + last N turns survive)."""

from __future__ import annotations

import json
import sqlite3

RAW_CONVERSATIONAL = ("question", "user_answer", "followup")
_ROLE_BY_TYPE = {"question": "assistant", "user_answer": "user", "followup": "assistant"}


def append(
    conn: sqlite3.Connection,
    session_id: int,
    turn_type: str,
    *,
    pattern: str | None = None,
    difficulty: str | None = None,
    question_id: str | None = None,
    verdict: str | None = None,
    advanced_manually: bool = False,
    mistake_note: str | None = None,
    payload: str | None = None,
) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO transcript "
            "(session_id, turn_type, pattern, difficulty, question_id, verdict, advanced_manually, mistake_note, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                turn_type,
                pattern,
                difficulty,
                question_id,
                verdict,
                int(advanced_manually),
                mistake_note,
                payload,
            ),
        )
    return cur.lastrowid


def turns(conn: sqlite3.Connection, session_id: int) -> list:
    return conn.execute(
        "SELECT id, turn_type, pattern, difficulty, question_id, verdict, "
        "advanced_manually, mistake_note, payload, summarized FROM transcript "
        "WHERE session_id = ? ORDER BY id",  # id is monotonic; ts may collide
        (session_id,),
    ).fetchall()


def conversation_context(conn: sqlite3.Connection, session_id: int, last_n: int) -> list[dict]:
    rows = conn.execute(
        "SELECT turn_type, payload FROM transcript "
        "WHERE session_id = ? AND summarized = 0 ORDER BY id",
        (session_id,),
    ).fetchall()
    turns_ = [
        {"role": _ROLE_BY_TYPE[r["turn_type"]], "content": r["payload"] or ""}
        for r in rows
        if r["turn_type"] in RAW_CONVERSATIONAL
    ]
    return turns_[-last_n:]


def mark_summarized(conn: sqlite3.Connection, ids: list[int]) -> None:
    if not ids:
        return
    with conn:
        conn.executemany(
            "UPDATE transcript SET summarized = 1 WHERE id = ?",
            [(i,) for i in ids],
        )


def summary(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    row = conn.execute(
        "SELECT compacted_summary FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"no session {session_id}")
    return json.loads(row["compacted_summary"] or "[]")


def set_summary(conn: sqlite3.Connection, session_id: int, entries: list[dict]) -> None:
    with conn:
        conn.execute(
            "UPDATE sessions SET compacted_summary = ? WHERE id = ?",
            (json.dumps(entries), session_id),
        )


def summary_text(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    return summary(conn, session_id)