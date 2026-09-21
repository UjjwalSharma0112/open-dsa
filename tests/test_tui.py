import asyncio
import json
import time
from dataclasses import replace
from pathlib import Path

import pytest

from opendsa import config as cfgmod
from opendsa import db, session, transcript
from opendsa.tui.app import StudyApp


class FakeAdapter:
    def __init__(self, numb: int) -> None:
        self.numb = numb

    def generate(self, system: str, history: list[dict]) -> str:
        if any("problem_number" in m.get("content", "") for m in history):
            return json.dumps(
                {
                    "title": "Delivery Trucks",
                    "story": "# Delivery Trucks\n\nTwo delivery trucks must coordinate - describe the approach.\n\n```python\na = [1, 2]\n```",
                    "problem_number": self.numb,
                }
            )
        return json.dumps({"verdict": "correct", "explanation": "spot on", "mistake_note": None})

    def stream(self, system: str, history: list[dict]):
        yield self.generate(system, history)


class SlowAdapter(FakeAdapter):
    def generate(self, system: str, history: list[dict]) -> str:
        time.sleep(0.3)
        return super().generate(system, history)


def _turns(conn, sid) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM transcript WHERE session_id = ?", (sid,)
    ).fetchone()[0]


async def _wait_until(pred, timeout: float = 5.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return True
        await asyncio.sleep(0.05)
    return False


def _harness(tmp_path: Path):
    base = cfgmod.load_config()
    cfg = replace(base, app=replace(base.app, database_path=tmp_path / "tui.db"))
    conn = db.connect(cfg.app.database_path)
    session.seed(conn, cfg)

    async def drive() -> str:
        app = StudyApp(cfg=cfg, conn=conn, adapter=FakeAdapter(numb=11), model="fake", force_new=True)
        async with app.run_test() as pilot:
            await pilot.pause(0.2)
            await pilot.press("enter")  # Start Screen -> begin session
            started = await _wait_until(lambda: session.latest_active(conn) is not None)
            sid = session.latest_active(conn)
            for answer in ["hashmap-based pairing works in O(n)", "/quit"]:
                bar = app.query_one("#answer")
                bar.focus()
                bar.text = answer
                await pilot.press("ctrl+enter")
                await pilot.pause(0.2)
            ok = started and sid is not None and await _wait_until(lambda: _turns(conn, sid) >= 4)
            app.exit()
            return "ok" if ok else "timeout"

    verdict = asyncio.run(drive())

    sid = conn.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()["id"]
    rows = transcript.turns(conn, sid)
    conn.close()
    return verdict, rows


def test_tui_starts_resumes_answers_and_ends(tmp_path: Path) -> None:
    verdict, rows = _harness(tmp_path)
    assert verdict == "ok"
    types = [r["turn_type"] for r in rows]
    assert types[:4] == ["question", "user_answer", "verdict", "link"]
    assert rows[2]["verdict"] == "correct"
    assert rows[0]["question_id"] == "lc-11"


def test_tui_resume_screen_shown_for_existing_session(tmp_path: Path) -> None:
    base = cfgmod.load_config()
    cfg = replace(base, app=replace(base.app, database_path=tmp_path / "tui2.db"))
    conn = db.connect(cfg.app.database_path)
    session.seed(conn, cfg)
    session.open_new(conn, "fake")

    async def drive() -> str:
        app = StudyApp(cfg=cfg, conn=conn, adapter=FakeAdapter(numb=11), model="fake")
        async with app.run_test() as pilot:
            await pilot.pause(0.2)
            name = type(app.screen).__name__
            app.exit()
            return name

    result = asyncio.run(drive())
    conn.close()
    assert result == "ResumeScreen"


def test_tui_inline_busy_footer_and_chip_text(tmp_path: Path) -> None:
    base = cfgmod.load_config()
    cfg = replace(base, app=replace(base.app, database_path=tmp_path / "tui3.db"))
    conn = db.connect(cfg.app.database_path)
    session.seed(conn, cfg)

    async def drive() -> tuple[bool, str, str, str, bool]:
        app = StudyApp(cfg=cfg, conn=conn, adapter=SlowAdapter(numb=11), model="fake", force_new=True)
        async with app.run_test() as pilot:
            await pilot.pause(0.2)
            await pilot.press("enter")
            await pilot.pause(0.1)  # generation in flight -> footer is busy
            busy_during = app.query_one("#status").has_class("busy")
            footer_during = app.query_one("#status-text").render().plain
            generation_chip = app.query_one("#chip").render().plain
            await pilot.pause(0.6)
            busy_after = app.query_one("#status").has_class("busy")
            ask_chip = app.query_one("#chip").render().plain
            app.exit()
            return busy_during, footer_during, generation_chip, f"{busy_after}|{ask_chip}", False

    busy_during, footer_during, generation_chip, after_state, _ = asyncio.run(drive())
    conn.close()
    assert busy_during is True
    assert "Generating question" in footer_during
    assert generation_chip == "[ GENERATING ]"
    assert after_state == "False|[ ASK ]"