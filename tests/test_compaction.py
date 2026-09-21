from dataclasses import replace
from pathlib import Path

import pytest

from opendsa import config as cfgmod
from opendsa import compaction, db, transcript


@pytest.fixture
def cfg():
    base = cfgmod.load_config()
    context = replace(base.context, last_n_turns=3)
    model = replace(base.model, context_window_tokens=1000)
    return replace(base, context=context, model=model)


@pytest.fixture
def conn(tmp_path: Path):
    c = db.connect(tmp_path / "comp.db")
    cur = c.execute("INSERT INTO sessions (model) VALUES ('fake')")
    c.commit()
    return c, cur.lastrowid


def test_estimate_tokens_grows_with_length() -> None:
    short = compaction.estimate_tokens("x")
    long_ = compaction.estimate_tokens("x" * 1000)
    assert short >= 1
    assert long_ > short


def test_build_entries_only_unsummarized_verdicts(conn) -> None:
    c, sid = conn
    transcript.append(c, sid, "question", pattern="a", payload="q")
    tid = transcript.append(c, sid, "verdict", pattern="a", verdict="wrong", mistake_note="m", payload="e")
    rows = transcript.turns(c, sid)
    assert len(compaction.build_entries(rows)) == 1
    transcript.mark_summarized(c, [tid])
    assert compaction.build_entries(transcript.turns(c, sid)) == []


def test_compact_folds_older_and_keeps_last_n(cfg, conn) -> None:
    c, sid = conn
    for i in range(8):
        if i % 2 == 1:
            transcript.append(c, sid, "verdict", pattern="p", verdict="wrong", mistake_note="m")
        else:
            transcript.append(c, sid, "user_answer", payload=f"content-{i}")
    rows = transcript.turns(c, sid)
    fixed = compaction.estimate_tokens("x" * 4000)  # fixed cost alone clears the 700-token budget
    ran = compaction.compact(c, cfg, sid, fixed, rows)
    assert ran is True

    after = transcript.turns(c, sid)
    kept = [r for r in after if r["summarized"] == 0]
    assert len(kept) == 3
    assert all(r["summarized"] == 1 for r in after[:-3])
    entries = transcript.summary(c, sid)
    assert any(e["pattern"] == "p" and e["verdict"] == "wrong" for e in entries)


def test_compact_is_noop_below_threshold(cfg, conn) -> None:
    c, sid = conn
    transcript.append(c, sid, "question", payload="short")
    rows = transcript.turns(c, sid)
    ran = compaction.compact(c, cfg, sid, 1, rows)
    assert ran is False
    assert transcript.summary(c, sid) == []