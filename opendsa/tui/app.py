"""open-dsa Textual study app.

Flow (per TUI-GUIDE.MD):
- on launch: Resume screen if an active session exists, else Start screen
  (--new bypasses resume).
- Start/Resume hands a session_id to ``_begin``, which runs a StudyController
  on a worker thread. The controller talks to the UI through ``UIOutput``
  (structured events) — no widget ever calls Gemini directly.
- The main screen is: header + (progress panel | question + conversation)
  + answer TextArea + status bar. Enter (or Ctrl+Enter) submits; commands like
  /help, /progress, /panel are handled here, the rest travel to the controller.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Markdown, Static, TextArea

from .. import progress, session
from ..config import Config
from ..controller import ControllerQuit, StudyController
from ..domain import display_pattern
from . import theme
from .output import UIOutput
from .screens import (
    ErrorScreen,
    HelpScreen,
    ProgressScreen,
    ResumeScreen,
    StartScreen,
)
from .widgets import STATUS_DEFAULT, AnswerBox, Conversation, StatusBar

DEFAULT_HINT = ""


class StudyApp(App[None]):
    TITLE = "open-dsa"
    CSS = theme.CSS

    BINDINGS = [
        Binding("ctrl+enter", "submit", "Submit"),
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def __init__(
        self,
        cfg: Config,
        conn: sqlite3.Connection,
        adapter: Any,
        model: str,
        force_new: bool = False,
    ) -> None:
        super().__init__()
        self.register_theme(theme.THEME)
        self.theme = "opendsa-dark"
        self._cfg = cfg
        self._conn = conn
        self._adapter = adapter
        self._model = model
        self._force_new = force_new
        self._session_id: int | None = None
        self._io: UIOutput | None = None
        self._controller: StudyController | None = None
        self._thread: threading.Thread | None = None
        self._finished = False
        self._error_detail = ""

    # -- composition --------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Static("open-dsa", id="brand")
            yield Static(DEFAULT_HINT, id="hint")
            yield Static("", id="chip")
        with Horizontal(id="body"):
            with VerticalScroll(id="panel"):
                yield Static("PROGRESS", id="panel-title")
                yield Static("", id="panel-body")
            yield Conversation()
        with Vertical(id="input-wrap"):
            yield AnswerBox(
                placeholder="Enter to submit your approach…",
                soft_wrap=True,
                id="answer",
            )
        yield StatusBar()

    def on_mount(self) -> None:
        existing = session.latest_active(self._conn)
        if self._force_new or existing is None:
            self.push_screen(
                StartScreen(
                    self._cfg.curriculum,
                    self._cfg.model.provider,
                    self._model,
                    on_start=self._handle_start,
                )
            )
        else:
            self.push_screen(
                ResumeScreen(
                    self._resume_info(existing),
                    on_resume=lambda: self._handle_resume(existing),
                    on_new=self._handle_resume_new,
                )
            )

    # -- start / resume flow ------------------------------------------------

    def _handle_start(self) -> None:
        self.pop_screen()
        sid = session.open_new(self._conn, self._model)
        self._begin(sid)

    def _handle_resume(self, sid: int) -> None:
        self.pop_screen()
        self._begin(sid)

    def _handle_resume_new(self) -> None:
        self.pop_screen()
        sid = session.open_new(self._conn, self._model)
        self._begin(sid)

    def _resume_info(self, sid: int) -> dict:
        patterns = progress.load_all(self._conn)
        current = progress.active(patterns, list(self._cfg.curriculum))
        last = session.last_question(self._conn, sid) or {}
        pattern = last.get("pattern") or (current.pattern if current else "")
        info: dict = {"pattern": pattern, "difficulty": "", "lc": "", "attempts": 0, "streak": 0}
        qid = str(last.get("question_id") or "")
        if qid.startswith("lc-"):
            info["lc"] = qid[3:]
        row = next((p for p in patterns if p.pattern == pattern), None)
        if row is not None:
            info["difficulty"] = row.difficulty.value.title()
            info["attempts"] = row.attempts
            info["streak"] = row.correct_streak
        else:
            info["difficulty"] = self._cfg.difficulty.start.title()
        return info

    def _begin(self, sid: int) -> None:
        self._session_id = sid
        self._finished = False
        self._io = UIOutput(self)
        self._controller = StudyController(self._cfg, self._conn, sid, self._adapter, self._io)
        self._thread = threading.Thread(
            target=self._run_session, name="study-controller", daemon=True
        )
        self._thread.start()

    def _run_session(self) -> None:
        try:
            self._controller.run()
        except ControllerQuit:
            pass
        except Exception as exc:
            self._error_detail = f"{type(exc).__name__}: {exc}"
            self.call_from_thread(self._show_error)
            return
        self.call_from_thread(self._on_session_finished)

    def _show_error(self) -> None:
        self._hide_loading()
        self._finished = True
        self.push_screen(
            ErrorScreen(self._error_detail, on_retry=self._retry, on_quit=self._quit_app)
        )

    def _retry(self) -> None:
        self.pop_screen()
        self._begin(self._session_id or -1)

    def _quit_app(self) -> None:
        self.exit()

    def _on_session_finished(self) -> None:
        self._hide_loading()
        self._finished = True
        self._set_status("Session complete — Ctrl+C to quit")
        box = self.query_one("#answer", TextArea)
        box.placeholder = "Session complete — press Ctrl+C to quit"

    # -- controller -> UI (always on the app thread) ------------------------

    def render_question(self, index: int, question: Any) -> None:
        hint = " • ".join(
            part
            for part in (
                question.difficulty.value.title(),
                question.company or "",
            )
            if part
        )
        self.query_one("#hint", Static).update(hint)
        heading = f"Question {question.problem_number}"
        if question.title:
            heading += f" — {question.title}"
        convo = self.query_one(Conversation)
        convo.add_question(heading, question.story)
        self.refresh_panel()
        self.set_state("ASK")

    def set_state(self, name: str) -> None:
        chip = self.query_one("#chip", Static)
        cls = {
            "EVALUATING": "evaluating",
            "FOLLOW-UP": "followup",
            "RESOLVED": "resolved",
            "GENERATING": "generating",
        }.get(name, "")
        chip.set_classes(cls)
        chip.update(f"\\[ {name} ]")
        if name == "GENERATING":
            self._show_loading("Generating question…")
        elif name == "EVALUATING":
            self._show_loading("Evaluating your approach…")
        else:
            self._hide_loading()

    # -- inline busy footer (replaces any blocking load modal) --------------

    def _show_loading(self, message: str) -> None:
        self.query_one(StatusBar).busy(message)

    def _hide_loading(self) -> None:
        self.query_one(StatusBar).idle()

    def convo_user(self, text: str) -> None:
        self.query_one(Conversation).add_user(text)

    def convo_assistant(self, text: str) -> None:
        self._hide_loading()
        self.query_one(Conversation).add_assistant(text)

    def convo_stream(self, chunk: str) -> None:
        self._hide_loading()
        self.query_one(Conversation).stream(chunk)

    def convo_stream_end(self) -> None:
        self.query_one(Conversation).end_stream()

    def convo_followup(self, text: str, used: int, cap: int) -> None:
        self._hide_loading()
        self.query_one(Conversation).add_followup(text, used, cap)

    def convo_verdict(self, label: str) -> None:
        self._hide_loading()
        self.query_one(Conversation).add_verdict(label)

    def convo_note(self, text: str) -> None:
        self.query_one(Conversation).add_note(text)

    def convo_link(self, number: int) -> None:
        self._hide_loading()
        self.query_one(Conversation).add_link(number)

    def demand(self, prompt: str) -> None:
        box = self.query_one("#answer", TextArea)
        box.clear()
        box.placeholder = prompt
        self._set_status()
        box.focus()

    def refresh_panel(self) -> None:
        patterns = progress.load_all(self._conn)
        current = progress.active(patterns, list(self._cfg.curriculum))
        lines: list[str] = []
        for p in patterns:
            filled = min(p.attempts, 8)
            bar = "█" * filled + "░" * (8 - filled)
            lines.append(f"{display_pattern(p.pattern):<16} {bar}")
        lines.append("")
        if current is not None:
            lines.append(f"Current: {display_pattern(current.pattern)}")
            lines.append(f"Difficulty: {current.difficulty.value.title()}")
            lines.append(f"Attempts: {current.attempts}")
            lines.append(f"Streak: {current.correct_streak}")
        self.query_one("#panel-body", Static).update("\n".join(lines))

    # -- input ----------------------------------------------------------------

    def _set_status(self, text: str = "") -> None:
        self.query_one(StatusBar).set(text or STATUS_DEFAULT)

    def action_submit(self) -> None:
        if self._io is None or self._finished or (self._thread and not self._thread.is_alive()):
            return
        box = self.query_one("#answer", TextArea)
        value = box.text.rstrip()
        if not value.strip():
            return
        box.clear()
        low = value.strip().lower()
        if low == "/help":
            self.push_screen(HelpScreen())
            return
        if low in {"/progress", "/history"}:
            self.push_screen(self._make_progress_screen())
            return
        if low == "/panel":
            panel = self.query_one("#panel")
            panel.set_class(not panel.has_class("visible"), "visible")
            return
        self._io.deliver(value)

    def _make_progress_screen(self) -> ProgressScreen:
        patterns = progress.load_all(self._conn)
        current = progress.active(patterns, list(self._cfg.curriculum))
        return ProgressScreen(patterns, current, self._cfg.curriculum)