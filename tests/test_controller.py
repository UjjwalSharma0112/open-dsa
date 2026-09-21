import json
import random
from dataclasses import replace
from pathlib import Path

import pytest

from opendsa import config as cfgmod
from opendsa import progress, session, transcript
from opendsa.controller import StudyController, _parse_json
from opendsa.domain import Difficulty, Verdict


class FakeAdapter:
    def __init__(self, gens: list[tuple[int, str]], evals: list[dict]) -> None:
        self.gens = list(gens)
        self.evals = list(evals)
        self.calls: list[str] = []
        self.force_flags: list[bool] = []

    def generate(self, system: str, history: list[dict]) -> str:
        is_gen = any("problem_number" in m.get("content", "") for m in history)
        self.calls.append("gen" if is_gen else "eval")
        self.force_flags.append("MUST NOT be \"partial\"" in system)
        if is_gen:
            num, story = self.gens.pop(0)
            return json.dumps({"title": "T", "story": story, "problem_number": num})
        return json.dumps(self.evals.pop(0))

    def stream(self, system: str, history: list[dict]):
        yield self.generate(system, history)


class FakeIO:
    """Output implementation for tests — records every call by channel."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.asks: list[str] = []
        self.questions: list[tuple[int, object]] = []
        self.states: list[str] = []
        self.users: list[str] = []
        self.assistants: list[str] = []
        self.streams: list[str] = []
        self.stream_ends = 0
        self.followups: list[tuple[str, int, int]] = []
        self.verdicts: list[str] = []
        self.notes: list[str] = []
        self.links: list[int] = []

    def question(self, index: int, question) -> None:
        self.questions.append((index, question))

    def state(self, name: str) -> None:
        self.states.append(name)

    def user(self, text: str) -> None:
        self.users.append(text)

    def assistant(self, text: str) -> None:
        self.assistants.append(text)

    def stream(self, chunk: str) -> None:
        self.streams.append(chunk)

    def stream_end(self) -> None:
        self.stream_ends += 1

    def followup(self, text: str, used: int, cap: int) -> None:
        self.followups.append((text, used, cap))

    def verdict(self, label: str) -> None:
        self.verdicts.append(label)

    def note(self, text: str) -> None:
        self.notes.append(text)

    def link(self, number: int) -> None:
        self.links.append(number)

    def ask(self, prompt: str) -> str:
        self.asks.append(prompt)
        return self.answers.pop(0) if self.answers else "/quit"


@pytest.fixture
def cfg(tmp_path: Path) -> cfgmod.Config:
    base = cfgmod.load_config()
    app = replace(base.app, database_path=tmp_path / "ctrl.db")
    return replace(base, app=app)


@pytest.fixture
def screen(cfg):
    conn, sid, resumed = session.start(cfg, fresh=True, model="fake")
    assert resumed is False
    yield cfg, conn, sid
    conn.close()


def make_controller(cfg, conn, sid, adapter, io, seed: int = 7, **kw):
    return StudyController(cfg, conn, sid, adapter, io, rng=random.Random(seed), **kw)


def active_pattern(conn, cfg):
    return progress.active(progress.load_all(conn), list(cfg.curriculum))


def test_correct_first_try(screen) -> None:
    cfg, conn, sid = screen
    adapter = FakeAdapter(gens=[(11, "story-A")], evals=[{"verdict": "correct", "explanation": "spot on", "mistake_note": None}])
    io = FakeIO(["the two pointers meet in the middle"])
    make_controller(cfg, conn, sid, adapter, io).run_question(active_pattern(conn, cfg))

    p = progress._get(conn, "two_pointer")
    assert p.attempts == 1
    assert p.correct_streak == 1
    assert p.wrong_streak == 0
    types = [r["turn_type"] for r in transcript.turns(conn, sid)]
    assert types == ["question", "user_answer", "verdict", "link"]
    assert transcript.turns(conn, sid)[-1]["payload"] == "11"
    assert "lc-11" in progress.seen_ids(conn, "two_pointer")
    assert io.verdicts == ["✓ CORRECT"]
    assert io.links == [11]
    assert io.states[-1] == "RESOLVED"


def test_nonstreamed_render_when_output_lacks_stream(screen) -> None:
    cfg, conn, sid = screen
    adapter = FakeAdapter(gens=[(11, "s")], evals=[{"verdict": "correct", "explanation": "spot on", "mistake_note": None}])
    io = FakeIO(["answer"])
    make_controller(cfg, conn, sid, adapter, io, stream=False).run_question(active_pattern(conn, cfg))
    assert io.assistants == ["spot on"]
    assert io.stream_ends == 0


def test_two_wrongs_drop_difficulty(screen) -> None:
    cfg, conn, sid = screen
    adapter = FakeAdapter(
        gens=[(11, "s1"), (12, "s2")],
        evals=[
            {"verdict": "wrong", "explanation": "use two pointers", "mistake_note": "space"},
            {"verdict": "wrong", "explanation": "still wrong", "mistake_note": "time"},
        ],
    )
    io = FakeIO(["answer one", "answer two"])
    ctrl = make_controller(cfg, conn, sid, adapter, io)
    ctrl.run_question(active_pattern(conn, cfg))
    ctrl.run_question(active_pattern(conn, cfg))

    p = progress._get(conn, "two_pointer")
    assert p.difficulty is Difficulty.EASY
    assert p.attempts == 2
    assert p.wrong_streak == 2
    assert any("dropped to easy" in m for m in io.notes)
    assert io.verdicts == ["× WRONG", "× WRONG"]


def test_partial_loop_with_cap_resolves(screen) -> None:
    cfg, conn, sid = screen
    cfg = replace(cfg, doubts=replace(cfg.doubts, loop_cap=2))
    adapter = FakeAdapter(
        gens=[(11, "story")],
        evals=[
            {"verdict": "partial", "explanation": "keep going", "mistake_note": "x"},
            {"verdict": "partial", "explanation": "nearly", "mistake_note": "y"},
            {"verdict": "correct", "explanation": "finally", "mistake_note": None},
        ],
    )
    io = FakeIO(["initial answer", "doubt about edge case", "second doubt"])
    make_controller(cfg, conn, sid, adapter, io).run_question(active_pattern(conn, cfg))

    types = [r["turn_type"] for r in transcript.turns(conn, sid)]
    assert types == ["question", "user_answer", "followup", "followup", "verdict", "link"]
    verdict_rows = [r for r in transcript.turns(conn, sid) if r["turn_type"] == "verdict"]
    assert verdict_rows[0]["verdict"] == Verdict.CORRECT.value
    p = progress._get(conn, "two_pointer")
    assert p.correct_streak == 1
    assert [used for _, used, _ in io.followups] == [0, 1]
    assert io.verdicts == ["✓ CORRECT"]


def test_skip_is_advanced_manually(screen) -> None:
    cfg, conn, sid = screen
    adapter = FakeAdapter(gens=[(11, "story")], evals=[])
    io = FakeIO(["/skip"])
    make_controller(cfg, conn, sid, adapter, io).run_question(active_pattern(conn, cfg))

    p = progress._get(conn, "two_pointer")
    assert p.attempts == 0
    verdict_rows = [r for r in transcript.turns(conn, sid) if r["turn_type"] == "verdict"]
    assert verdict_rows[0]["verdict"] == Verdict.SKIP.value
    assert verdict_rows[0]["advanced_manually"] == 1
    assert any("Skipped" in m for m in io.notes)
    assert io.links == [11]
    assert io.states[-1] == "RESOLVED"


def test_reattempt_when_problem_seen(screen) -> None:
    cfg, conn, sid = screen
    adapter = FakeAdapter(
        gens=[(11, "first"), (22, "second")],
        evals=[{"verdict": "correct", "explanation": "ok", "mistake_note": None}],
    )
    progress.add_seen(conn, "two_pointer", "lc-11")
    io = FakeIO(["my answer"])
    make_controller(cfg, conn, sid, adapter, io).run_question(active_pattern(conn, cfg))
    assert adapter.gens == []
    assert any("Problem 11 already covered" in m for m in io.notes)
    assert "lc-22" in progress.seen_ids(conn, "two_pointer")


def test_mastery_advances_to_next_pattern(screen) -> None:
    cfg, conn, sid = screen
    cfg = replace(
        cfg, mastery=replace(cfg.mastery, min_attempts=1, min_correct_streak=1)
    )
    adapter = FakeAdapter(
        gens=[(11, "story")],
        evals=[{"verdict": "correct", "explanation": "ok", "mistake_note": None}],
    )
    io = FakeIO(["answer"])
    make_controller(cfg, conn, sid, adapter, io).run_question(active_pattern(conn, cfg))
    active = active_pattern(conn, cfg)
    assert active.pattern == "sliding_window"
    assert any("mastered" in m for m in io.notes)


def test_compaction_runs_inside_controller(screen) -> None:
    cfg, conn, sid = screen
    cfg = replace(
        cfg,
        context=replace(cfg.context, last_n_turns=2),
        model=replace(cfg.model, context_window_tokens=40),  # tiny budget -> 70% = 28 tokens
    )
    story = "Q" * 300
    adapter = FakeAdapter(
        gens=[(1, story), (2, story), (3, story)],
        evals=[
            {"verdict": "correct", "explanation": "ok", "mistake_note": None},
            {"verdict": "correct", "explanation": "ok", "mistake_note": None},
            {"verdict": "correct", "explanation": "ok", "mistake_note": None},
        ],
    )
    io = FakeIO(["a1", "a2", "a3"])
    ctrl = make_controller(cfg, conn, sid, adapter, io)
    for _ in range(3):
        ctrl.run_question(active_pattern(conn, cfg))

    entries = transcript.summary(conn, sid)
    assert len(entries) >= 1
    assert all(e["pattern"] == "two_pointer" for e in entries)
    turns = transcript.turns(conn, sid)
    summarized = [r for r in turns if r["summarized"] == 1]
    assert len(summarized) == 6  # questions 1 and 2's leading turns were folded away
    keep = [r for r in turns if r["summarized"] == 0]
    assert len(keep) == 6
    assert keep[-1]["turn_type"] == "link"  # newest raw turns survive


def test_parse_json_handles_fences() -> None:
    text = '```json\n{"story": "s", "problem_number": 11}\n```'
    assert _parse_json(text) == {"story": "s", "problem_number": 11}


def test_quit_ends_session(tmp_path) -> None:
    base = cfgmod.load_config()
    cfg = replace(base, app=replace(base.app, database_path=tmp_path / "q.db"))
    conn, sid, _ = session.start(cfg, fresh=True, model="fake")
    adapter = FakeAdapter(gens=[(1, "s")], evals=[])
    io = FakeIO(["/quit"])
    ctrl = StudyController(cfg, conn, sid, adapter, io)
    ctrl.run()
    assert "Session ended." in io.notes