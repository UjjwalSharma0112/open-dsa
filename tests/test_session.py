from dataclasses import replace
from pathlib import Path

from opendsa import config as cfgmod
from opendsa import session


def cfg(tmp_path: Path) -> cfgmod.Config:
    base = cfgmod.load_config()
    return replace(base, app=replace(base.app, database_path=tmp_path / "sess.db"))


def test_fresh_then_resume_then_fresh(tmp_path: Path) -> None:
    c = cfg(tmp_path)

    conn1, sid1, resumed1 = session.start(c, fresh=True, model="gemini-x")
    try:
        assert resumed1 is False
        n_patterns = conn1.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]
        assert n_patterns == len(c.curriculum)
    finally:
        conn1.close()

    conn2, sid2, resumed2 = session.start(c, fresh=False, model="gemini-x")
    try:
        assert resumed2 is True
        assert sid2 == sid1
    finally:
        conn2.close()

    conn3, sid3, resumed3 = session.start(c, fresh=True, model="gemini-x")
    try:
        assert resumed3 is False
        assert sid3 != sid1
    finally:
        conn3.close()


def test_no_existing_session_starts_fresh(tmp_path: Path) -> None:
    c = cfg(tmp_path)
    conn, sid, resumed = session.start(c, fresh=False, model="gemini-x")
    try:
        assert resumed is False
        session_id = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert session_id == 1
    finally:
        conn.close()