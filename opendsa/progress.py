"""Progress track (guidelines 2.6). Small, structured, always in-context.
Functions here are pure-ish over a sqlite Connection — no model/IO."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .config import Config
from .domain import Difficulty, ProgressPattern, Verdict, difficulty_from, drop_one


def load_all(conn: sqlite3.Connection) -> list[ProgressPattern]:
    rows = conn.execute(
        "SELECT pattern, position, status, difficulty, attempts, correct_streak, wrong_streak, mastered_at "
        "FROM patterns ORDER BY position"
    ).fetchall()
    return [
        ProgressPattern(
            pattern=r["pattern"],
            position=r["position"],
            status=r["status"],
            difficulty=difficulty_from(r["difficulty"]),
            attempts=r["attempts"],
            correct_streak=r["correct_streak"],
            wrong_streak=r["wrong_streak"],
            mastered_at=r["mastered_at"],
        )
        for r in rows
    ]


def active(patterns: list[ProgressPattern], curriculum: list[str]) -> ProgressPattern | None:
    wanted = {p: i for i, p in enumerate(curriculum)}
    active_ones = [p for p in patterns if p.status != "mastered"]
    active_ones.sort(key=lambda p: (wanted.get(p.pattern, len(curriculum)), p.position))
    return active_ones[0] if active_ones else None


def seen_ids(conn: sqlite3.Connection, pattern: str) -> set[str]:
    rows = conn.execute(
        "SELECT question_id FROM questions_seen WHERE pattern = ?", (pattern,)
    ).fetchall()
    return {r["question_id"] for r in rows}


def add_seen(conn: sqlite3.Connection, pattern: str, question_id: str) -> None:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO questions_seen (pattern, question_id) VALUES (?, ?)",
            (pattern, question_id),
        )


def _row_to_pattern(row) -> ProgressPattern:
    return ProgressPattern(
        pattern=row["pattern"],
        position=row["position"],
        status=row["status"],
        difficulty=difficulty_from(row["difficulty"]),
        attempts=row["attempts"],
        correct_streak=row["correct_streak"],
        wrong_streak=row["wrong_streak"],
        mastered_at=row["mastered_at"],
    )


def record_scored(
    conn: sqlite3.Connection,
    cfg: Config,
    pattern: str,
    verdict: Verdict,
) -> ProgressPattern:
    """Apply a resolved verdict to the progress track. SKIP is a no-op."""
    if verdict is Verdict.SKIP:
        return _get(conn, pattern)

    attempts_inc = 1  # correct and wrong both count as attempts
    with conn:
        if verdict is Verdict.CORRECT:
            conn.execute(
                "UPDATE patterns SET attempts = attempts + ?, correct_streak = correct_streak + 1, "
                "wrong_streak = 0 WHERE pattern = ?",
                (attempts_inc, pattern),
            )
        else:
            conn.execute(
                "UPDATE patterns SET attempts = attempts + ?, correct_streak = 0, "
                "wrong_streak = wrong_streak + 1 WHERE pattern = ?",
                (attempts_inc, pattern),
            )
    row = _get(conn, pattern)
    if row.status == "active" and _mastered(cfg, row):
        row = _master(conn, pattern)
    return row


def _mastered(cfg: Config, p: ProgressPattern) -> bool:
    return (
        p.attempts >= cfg.mastery.min_attempts
        and p.correct_streak >= cfg.mastery.min_correct_streak
    )


def _master(conn: sqlite3.Connection, pattern: str) -> ProgressPattern:
    with conn:
        conn.execute(
            "UPDATE patterns SET status = 'mastered', mastered_at = ? WHERE pattern = ?",
            (datetime.now(timezone.utc).isoformat(), pattern),
        )
    return _get(conn, pattern)


def maybe_drop_difficulty(
    conn: sqlite3.Connection, p: ProgressPattern, min_drop_streak: int = 2
) -> ProgressPattern:
    """Guideline 2.6: two consecutive wrongs -> one tier down (floor Easy)."""
    if p.wrong_streak < min_drop_streak:
        return p
    new = drop_one(p.difficulty)
    if new is p.difficulty:
        return p
    with conn:
        conn.execute(
            "UPDATE patterns SET difficulty = ? WHERE pattern = ?",
            (new.value, p.pattern),
        )
    return _get(conn, p.pattern)


def set_difficulty(conn: sqlite3.Connection, pattern: str, difficulty: Difficulty) -> None:
    with conn:
        conn.execute(
            "UPDATE patterns SET difficulty = ? WHERE pattern = ?",
            (difficulty.value, pattern),
        )


def mark_mastered(conn: sqlite3.Connection, pattern: str) -> None:
    with conn:
        conn.execute(
            "UPDATE patterns SET status = 'mastered', mastered_at = ? WHERE pattern = ?",
            (datetime.now(timezone.utc).isoformat(), pattern),
        )


def _get(conn: sqlite3.Connection, pattern: str) -> ProgressPattern:
    row = conn.execute(
        "SELECT pattern, position, status, difficulty, attempts, correct_streak, wrong_streak, mastered_at "
        "FROM patterns WHERE pattern = ?",
        (pattern,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown pattern: {pattern}")
    return _row_to_pattern(row)