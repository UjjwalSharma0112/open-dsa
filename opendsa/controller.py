"""Per-question state machine and session driver (guidelines 2.3, FR4-FR10).

Flow: ASK -> EVALUATE -> {correct | partial | wrong | skip} -> LOG -> next.
Pure logic — no UI import. Talks to the world only through an ``Output``
protocol and a ModelAdapter, so it is fully testable without Textual.

The ``Output`` protocol is structured (per-section rendering hooks) so a UI
can render a question page, a verdict chip, streaming text, etc. instead of
parsing a flat text stream.
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
from typing import Protocol

from . import compaction, db, progress, prompts, transcript
from .adapters.base import ModelAdapter
from .config import Config
from .domain import Question, Verdict, display_pattern, verdict_from


class ControllerQuit(Exception):
    pass


class Output(Protocol):
    """Everything the controller tells the UI, plus the one blocking ask().

    ``stream``/``stream_end`` are optional: if the UI implements them, the
    controller uses the adapter's streaming path and renders progress live.
    """

    def question(self, index: int, question: Question) -> None: ...
    def state(self, name: str) -> None: ...
    def user(self, text: str) -> None: ...
    def assistant(self, text: str) -> None: ...
    def stream(self, chunk: str) -> None: ...
    def stream_end(self) -> None: ...
    def followup(self, text: str, used: int, cap: int) -> None: ...
    def verdict(self, label: str) -> None: ...
    def note(self, text: str) -> None: ...
    def link(self, number: int) -> None: ...
    def ask(self, prompt: str) -> str: ...


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    return json.loads(match.group(0))


_CODE_FENCE = re.compile(r"```[A-Za-z0-9_-]*")


def _clean_stream_text(text: str) -> str:
    """Drop markdown code-fence markers (```` ```json ````, `` ``` ``) that
    models sometimes wrap the verdict JSON in, so fences never leak into the
    conversation as raw text."""
    return _CODE_FENCE.sub("", text)


class StudyController:
    def __init__(
        self,
        cfg: Config,
        conn: sqlite3.Connection,
        session_id: int,
        adapter: ModelAdapter,
        out: Output,
        rng: random.Random | None = None,
        *,
        stream: bool | None = None,
    ) -> None:
        self.cfg = cfg
        self.conn = conn
        self.session_id = session_id
        self.adapter = adapter
        self.out = out
        self._rng = rng or random.Random()
        self._company_pool = list(cfg.flavor.companies)
        if stream is None:
            stream = hasattr(out, "stream") and hasattr(adapter, "stream")
        self._streaming = stream

    # -- public driver -----------------------------------------------------

    def run(self) -> None:
        while True:
            patterns = progress.load_all(self.conn)
            current = progress.active(patterns, list(self.cfg.curriculum))
            if current is None:
                self.out.note(
                    "Curriculum complete. Every pattern is mastered. Press Ctrl+C to exit."
                )
                return
            try:
                self.run_question(current)
            except ControllerQuit:
                self.out.note("Session ended.")
                return

    def run_question(self, pat: progress.ProgressPattern) -> None:
        self._compact_if_needed()
        self.out.state("GENERATING")
        seen = progress.seen_ids(self.conn, pat.pattern)
        company = self._pick_company()
        question = self._generate(pat, company, seen)
        if question.question_id in seen:  # FR3: no repeats — retry once
            self.out.note(
                f"Problem {question.problem_number} already covered; picking a new one."
            )
            retry = self._generate(pat, company, seen)
            if retry.question_id not in seen:
                question = retry
        self._log_question(question)
        index = self._question_index()
        self.out.question(index, question)

        kind, raw = self._user_turn(
            "Your approach/answer (or /skip, /next, /quit):", allow_resolve=False
        )
        if kind == "skip":
            self._finalize(question, Verdict.SKIP, None, None, advanced=True, streamed=False)
            return
        self.out.user(raw)
        self._append_user_turn(raw, followup=False)
        verdict, explanation, mistake, streamed = self._evaluate(question, force=False)
        if verdict is Verdict.PARTIAL:
            outcome = self._doubt_loop(question, explanation, streamed)
            if outcome is None:
                return
            verdict, explanation, mistake, streamed = outcome
        self._finalize(question, verdict, explanation, mistake, advanced=False, streamed=streamed)

    # -- generation ---------------------------------------------------------

    def _pick_company(self) -> str | None:
        if not self._company_pool:
            return None
        return self._rng.choice(self._company_pool)

    def _generate(
        self,
        pat: progress.ProgressPattern,
        company: str | None,
        seen: set[str],
    ) -> Question:
        seen_numbers = []
        for sid in seen:
            if sid.startswith("lc-") and sid[3:].isdigit():
                seen_numbers.append(int(sid[3:]))
        content = prompts.generation_user_message(
            pat.pattern, pat.difficulty.value, company, seen_numbers
        )
        text = self.adapter.generate(
            prompts.system_prompt(), [{"role": "user", "content": content}]
        )
        parsed = _parse_json(text)
        story = str(parsed.get("story", "")).strip()
        if not story:
            raise ValueError(f"empty story from model: {text[:200]!r}")
        return Question(
            pattern=pat.pattern,
            difficulty=pat.difficulty,
            company=company,
            problem_number=int(parsed["problem_number"]),
            story=story,
            title=str(parsed.get("title", "")).strip(),
        )

    # -- evaluation ---------------------------------------------------------

    def _evaluate(
        self, question: Question, *, force: bool
    ) -> tuple[Verdict, str, str | None, bool]:
        """Returns (verdict, explanation, mistake_note, was_streamed)."""
        system = prompts.system_prompt() + prompts.evaluation_block(force=force)
        history = transcript.conversation_context(
            self.conn, self.session_id, self.cfg.context.last_n_turns
        )
        if self._streaming:
            return self._evaluate_streamed(system, history)

        text = self.adapter.generate(system, history)
        parsed = _parse_json(text)
        v = verdict_from(parsed["verdict"])
        return v, str(parsed.get("explanation", "")), parsed.get("mistake_note"), False

    def _evaluate_streamed(
        self, system: str, history: list[dict]
    ) -> tuple[Verdict, str, str | None, bool]:
        """Stream conversational output live; the JSON tail is swallowed.

        Fences around the JSON are stripped and the JSON itself (and anything
        after it) is hidden. ``streamed`` is True only when actual prose was
        forwarded — if the model returns nothing but JSON, the caller renders
        the explanation as a normal assistant turn instead.
        """
        chunks: list[str] = []
        streamed_text = False
        in_json = False
        for chunk in self.adapter.stream(system, history):
            chunks.append(chunk)
            if not in_json:
                json_at = chunk.find("{")
                forward = _clean_stream_text(
                    chunk[:json_at] if json_at >= 0 else chunk
                ).strip()
                if json_at >= 0:
                    in_json = True
                if forward:
                    streamed_text = True
                    self.out.stream(forward)
        self.out.stream_end()
        text = "".join(chunks)
        parsed = _parse_json(text)
        v = verdict_from(parsed["verdict"])
        return v, str(parsed.get("explanation", "")), parsed.get("mistake_note"), streamed_text

    def _doubt_loop(
        self, question: Question, explanation: str, streamed: bool
    ) -> tuple[Verdict, str, str | None, bool] | None:
        cap = self.cfg.doubts.loop_cap
        followups = 0
        while True:
            self.out.state("FOLLOW-UP")
            self.out.followup(explanation, followups, cap)
            kind, raw = self._user_turn(
                "Your doubt (or /resolve to force a verdict, /skip, /next, /quit):",
                allow_resolve=True,
            )
            if kind == "skip":
                self._finalize(question, Verdict.SKIP, None, None, advanced=True, streamed=False)
                return None
            if kind == "resolve":
                verdict, explanation, mistake, streamed = self._evaluate(question, force=True)
            else:
                self.out.user(raw)
                self._append_user_turn(raw, followup=True)
                followups += 1
                force = followups >= cap
                verdict, explanation, mistake, streamed = self._evaluate(question, force=force)
            if verdict is not Verdict.PARTIAL:
                return verdict, explanation, mistake, streamed
            if followups >= cap:
                verdict, explanation, mistake, streamed = self._evaluate(question, force=True)
                return verdict, explanation, mistake, streamed

    # -- resolution ---------------------------------------------------------

    def _finalize(
        self,
        question: Question,
        verdict: Verdict,
        explanation: str | None,
        mistake: str | None,
        *,
        advanced: bool,
        streamed: bool,
    ) -> None:
        if verdict is Verdict.SKIP:
            self.out.note("Skipped — no mastery credit.")
            self._log_verdict(question, verdict, explanation, mistake, advanced=advanced)
            self._log_link(question)
            progress.add_seen(self.conn, question.pattern, question.question_id)
            self.out.note(f"Pattern: {display_pattern(question.pattern)}")
            self.out.link(question.problem_number)
            self.out.state("RESOLVED")
            return

        updated = progress.record_scored(self.conn, self.cfg, question.pattern, verdict)
        if verdict is Verdict.WRONG:
            if explanation and not streamed:
                self.out.assistant(explanation)
            self.out.verdict("× WRONG")
            lowered = progress.maybe_drop_difficulty(self.conn, updated)
            if lowered.difficulty is not updated.difficulty:
                self.out.note(
                    f"Difficulty for {display_pattern(question.pattern)} dropped to {lowered.difficulty.value}."
                )
        elif verdict is Verdict.CORRECT:
            if explanation and not streamed:
                self.out.assistant(explanation)
            self.out.verdict("✓ CORRECT")
            if updated.status == "mastered":
                self.out.note(
                    f"{display_pattern(question.pattern)} mastered — moving to the next pattern."
                )
        self.out.note(f"Pattern: {display_pattern(question.pattern)}")
        self._log_verdict(question, verdict, explanation, mistake, advanced=advanced)
        self._log_link(question)
        progress.add_seen(self.conn, question.pattern, question.question_id)
        self.out.link(question.problem_number)
        db.seed_bank(
            self.conn,
            [
                {
                    "question_id": question.question_id,
                    "pattern": question.pattern,
                    "difficulty": question.difficulty.value,
                }
            ],
        )
        self.out.state("RESOLVED")

    # -- logging ------------------------------------------------------------

    def _log_question(self, question: Question) -> None:
        transcript.append(
            self.conn,
            self.session_id,
            "question",
            pattern=question.pattern,
            difficulty=question.difficulty.value,
            question_id=question.question_id,
            payload=question.story,
        )

    def _append_user_turn(self, raw: str, *, followup: bool) -> None:
        transcript.append(
            self.conn,
            self.session_id,
            "followup" if followup else "user_answer",
            payload=raw,
        )

    def _log_verdict(
        self,
        question: Question,
        verdict: Verdict,
        explanation: str | None,
        mistake: str | None,
        *,
        advanced: bool,
    ) -> None:
        transcript.append(
            self.conn,
            self.session_id,
            "verdict",
            pattern=question.pattern,
            difficulty=question.difficulty.value,
            question_id=question.question_id,
            verdict=verdict.value,
            advanced_manually=advanced,
            mistake_note=mistake,
            payload=explanation,
        )

    def _log_link(self, question: Question) -> None:
        transcript.append(
            self.conn,
            self.session_id,
            "link",
            pattern=question.pattern,
            difficulty=question.difficulty.value,
            question_id=question.question_id,
            payload=str(question.problem_number),
        )

    # -- interaction / input ------------------------------------------------

    def _user_turn(self, prompt: str, *, allow_resolve: bool = False) -> tuple[str, str]:
        while True:
            text = self.out.ask(prompt)
            stripped = text.strip()
            low = stripped.lower()
            if low in {"/skip", "/next"}:
                return "skip", stripped
            if low == "/quit":
                raise ControllerQuit
            if low == "/resolve" and allow_resolve:
                return "resolve", stripped
            if low.startswith("/"):
                self.out.note(f"Unknown command: {stripped}")
                continue
            if not stripped:
                continue
            return "answer", stripped

    # -- helpers ------------------------------------------------------------

    def _question_index(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM transcript "
            "WHERE session_id = ? AND turn_type = 'question'",
            (self.session_id,),
        ).fetchone()
        return int(row["c"]) + 1

    def _compact_if_needed(self) -> None:
        rows = transcript.turns(self.conn, self.session_id)
        if not rows:
            return
        fixed = compaction.estimate_tokens(prompts.system_prompt())
        compaction.compact(self.conn, self.cfg, self.session_id, fixed, rows)