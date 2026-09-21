"""Compaction (guidelines 2.5). Token-count triggered, targets only the raw
transcript portion of context; the progress track is exempt. Output is a short
structured summary per resolved question, not free-text recap."""

from __future__ import annotations

import sqlite3

from .config import Config
from . import transcript

TOKENS_PER_CHAR = 4


def estimate_tokens(text: str) -> int:
    """Cheap deterministic estimator used for the trigger check."""
    return max(1, len(text or "") // TOKENS_PER_CHAR)


def context_budget(cfg: Config) -> int:
    return cfg.model.context_window_tokens * cfg.context.compaction_threshold_percent // 100


def build_entries(rows) -> list[dict]:
    """One structured entry per resolved question in the given transcript slice."""
    entries: list[dict] = []
    for r in rows:
        if r["verdict"] is None or r["summarized"]:
            continue
        entries.append(
            {
                "pattern": r["pattern"],
                "verdict": r["verdict"],
                "mistake": r["mistake_note"],
            }
        )
    return entries


def compact(
    conn: sqlite3.Connection,
    cfg: Config,
    session_id: int,
    fixed_cost: int,
    rows,
) -> bool:
    """If estimated context crosses the threshold, fold older resolved blocks
    into the session summary and mark them summarized. Returns True if it ran."""
    est = fixed_cost
    for r in rows:
        est += estimate_tokens(r["payload"] or "")
    if est < context_budget(cfg):
        return False

    last_n = cfg.context.last_n_turns
    older, keep = rows[:-last_n], rows[-last_n:]
    if not older:
        return False

    entries = build_entries(older)
    if entries:
        current = transcript.summary(conn, session_id)
        transcript.set_summary(conn, session_id, current + entries)
    transcript.mark_summarized(conn, [r["id"] for r in older])
    return True