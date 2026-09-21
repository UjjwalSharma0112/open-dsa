from dataclasses import replace
from pathlib import Path

import pytest

from opendsa import config as cfgmod
from opendsa import db, progress
from opendsa.domain import Difficulty, Verdict

CURRICULUM = ["two_pointer", "sliding_window"]


@pytest.fixture
def base_cfg() -> cfgmod.Config:
    return cfgmod.load_config()


@pytest.fixture
def conn(tmp_path: Path):
    c = db.connect(tmp_path / "prog.db")
    db.seed_patterns(c, CURRICULUM)
    try:
        yield c
    finally:
        c.close()


def test_correct_resets_wrong_streak(base_cfg, conn) -> None:
    conn.execute("UPDATE patterns SET wrong_streak = 3 WHERE pattern = 'two_pointer'")
    row = progress.record_scored(conn, base_cfg, "two_pointer", Verdict.CORRECT)
    assert row.attempts == 1
    assert row.correct_streak == 1
    assert row.wrong_streak == 0


def test_wrong_builds_streak_and_resets_correct(base_cfg, conn) -> None:
    conn.execute("UPDATE patterns SET correct_streak = 2 WHERE pattern = 'two_pointer'")
    row = progress.record_scored(conn, base_cfg, "two_pointer", Verdict.WRONG)
    assert row.attempts == 1
    assert row.wrong_streak == 1
    assert row.correct_streak == 0


def test_skip_is_noop(base_cfg, conn) -> None:
    row = progress.record_scored(conn, base_cfg, "two_pointer", Verdict.SKIP)
    assert row.attempts == 0
    assert row.wrong_streak == 0


def test_two_wrongs_drops_medium_to_easy(base_cfg, conn) -> None:
    for _ in range(2):
        p = progress.record_scored(conn, base_cfg, "two_pointer", Verdict.WRONG)
        p = progress.maybe_drop_difficulty(conn, p)
    assert p.difficulty is Difficulty.EASY


def test_drop_floored_at_easy(base_cfg, conn) -> None:
    progress.set_difficulty(conn, "two_pointer", Difficulty.EASY)
    conn.execute("UPDATE patterns SET wrong_streak = 4 WHERE pattern = 'two_pointer'")
    p = progress._get(conn, "two_pointer")
    p = progress.maybe_drop_difficulty(conn, p)
    assert p.difficulty is Difficulty.EASY


def test_mastery_requires_attempts_and_streak(base_cfg, conn) -> None:
    mastery = replace(base_cfg.mastery, min_attempts=1, min_correct_streak=1)
    cfg = replace(base_cfg, mastery=mastery)
    p = progress.record_scored(conn, cfg, "two_pointer", Verdict.CORRECT)
    assert p.status == "mastered"
    assert p.mastered_at is not None


def test_single_correct_not_mastered_with_default_thresholds(base_cfg, conn) -> None:
    p = progress.record_scored(conn, base_cfg, "two_pointer", Verdict.CORRECT)
    assert p.status == "active"


def test_active_skips_mastered(base_cfg, conn) -> None:
    # mastery needs attempts too; force it via mark_mastered
    progress.record_scored(conn, base_cfg, "two_pointer", Verdict.WRONG)
    progress.mark_mastered(conn, "two_pointer")
    patterns = progress.load_all(conn)
    active = progress.active(patterns, CURRICULUM)
    assert active is not None
    assert active.pattern == "sliding_window"