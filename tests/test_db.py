from pathlib import Path

import pytest

from opendsa import db

CORE_TABLES = {"sessions", "bank", "transcript", "patterns", "questions_seen"}


@pytest.fixture
def conn(tmp_path: Path):
    c = db.connect(tmp_path / "test.db")
    try:
        yield c
    finally:
        c.close()


def test_migrations_set_version(conn) -> None:
    row = conn.execute("PRAGMA user_version").fetchone()
    assert row[0] == db.SCHEMA_VERSION


def test_connect_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    db.connect(path).close()
    rerun = db.connect(path)
    try:
        assert rerun.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        names = {
            r[0]
            for r in rerun.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert CORE_TABLES <= names
        cols = {r[1] for r in rerun.execute("PRAGMA table_info(transcript)")}
        assert "summarized" in cols
        scol = {r[1] for r in rerun.execute("PRAGMA table_info(sessions)")}
        assert "compacted_summary" in scol
    finally:
        rerun.close()


def test_core_tables_and_indexes_exist(conn) -> None:
    names = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert CORE_TABLES <= names
    indexes = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert "idx_transcript_session" in indexes


def test_seed_patterns_idempotent_and_ordered(conn) -> None:
    curriculum = ["two_pointer", "sliding_window", "binary_search"]
    db.seed_patterns(conn, curriculum)
    rows = conn.execute("SELECT pattern, position FROM patterns ORDER BY position").fetchall()
    assert [tuple(r) for r in rows] == [
        ("two_pointer", 0),
        ("sliding_window", 1),
        ("binary_search", 2),
    ]
    db.seed_patterns(conn, ["two_pointer"])
    assert conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0] == 3


def test_seed_bank_idempotent(conn) -> None:
    rows = [
        {"question_id": "lc-11", "pattern": "two_pointer", "difficulty": "medium"},
        {"question_id": "lc-15", "pattern": "two_pointer", "difficulty": "medium"},
    ]
    db.seed_bank(conn, rows)
    db.seed_bank(conn, [rows[0]])
    assert conn.execute("SELECT COUNT(*) FROM bank").fetchone()[0] == 2


def test_seed_bank_rejects_bad_difficulty(conn) -> None:
    with pytest.raises(ValueError, match="difficulty"):
        db.seed_bank(conn, [{"question_id": "x", "pattern": "greedy", "difficulty": "harder"}])


def test_transcript_append_and_fkey(conn) -> None:
    cur = conn.execute("INSERT INTO sessions (model) VALUES (?)", ("gemini",))
    session_id = cur.lastrowid
    conn.execute(
        "INSERT INTO transcript (session_id, turn_type, verdict, payload) VALUES (?, ?, ?, ?)",
        (session_id, "question", "partial", "story text"),
    )
    row = conn.execute("SELECT * FROM transcript").fetchone()
    assert row["turn_type"] == "question"
    assert row["verdict"] == "partial"
    assert row["advanced_manually"] == 0
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO transcript (session_id, turn_type) VALUES (?, ?)",
            (999999, "question"),
        )