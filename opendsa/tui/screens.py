"""Modal screens: session start, resume, progress, help, error.

TUI-GUIDE.MD §14 (start), §15 (resume), §16 (progress), §19 (error).
Each screen is thin: it owns presentation and reports a choice through a
callback — no Gemini calls, no database writes.
"""

from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from ..domain import ProgressPattern, display_pattern


class StartScreen(ModalScreen[None]):
    """Welcome / setup screen shown for a brand-new session (spec §14)."""

    BINDINGS = [Binding("escape", "ignore", "ignore")]

    def __init__(
        self,
        curriculum: tuple[str, ...],
        provider: str,
        model: str,
        on_start: Callable[[], None],
    ) -> None:
        super().__init__()
        self._curriculum = curriculum
        self._provider = provider
        self._model = model
        self._on_start = on_start

    def action_ignore(self) -> None:
        pass

    def compose(self) -> ComposeResult:
        with Vertical(id="card"):
            yield Static("open-dsa", classes="card-title")
            yield Static("DSA Interview Practice", classes="card-sub")
            yield Static(
                "Story-based questions.\nExplain your approach.\nGet conversational feedback.",
                classes="card-line",
            )
            yield Static("", classes="card-rule")
            yield Static("Model", classes="card-title")
            yield Static(f"{self._provider.title()} — {self._model}", classes="card-line")
            yield Button("Start Session", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self._on_start()


class ResumeScreen(ModalScreen[None]):
    """'Resume previous session?' with Resume / New Session (spec §15)."""

    BINDINGS = [Binding("escape", "resume", "resume")]

    def __init__(
        self,
        info: dict,
        on_resume: Callable[[], None],
        on_new: Callable[[], None],
    ) -> None:
        super().__init__()
        self._info = info
        self._on_resume = on_resume
        self._on_new = on_new

    def action_resume(self) -> None:
        self._on_resume()

    def compose(self) -> ComposeResult:
        sub = []
        diff = self._info.get("difficulty") or ""
        if diff:
            sub.append(diff)
        if self._info.get("lc"):
            sub.append(f"Question {self._info['lc']}")
        with Vertical(id="card"):
            yield Static("Resume previous session?", classes="card-title")
            yield Static(display_pattern(self._info["pattern"]), classes="card-title")
            if sub:
                yield Static(" • ".join(sub), classes="card-sub")
            yield Static(
                f"Attempts: {self._info.get('attempts', 0)}   "
                f"Correct streak: {self._info.get('streak', 0)}",
                classes="card-line",
            )
            with Horizontal():
                yield Button("Resume", variant="primary")
                yield Button("New Session")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.label is not None and "Resume" in str(event.button.label):
            self._on_resume()
        else:
            self._on_new()


class ProgressScreen(ModalScreen[None]):
    """Dedicated informational progress view (spec §16, open via /progress)."""

    BINDINGS = [Binding("escape", "close", "close")]

    def action_close(self) -> None:
        self.app.pop_screen()

    def __init__(
        self,
        patterns: list[ProgressPattern],
        current: ProgressPattern | None,
        curriculum: tuple[str, ...],
    ) -> None:
        super().__init__()
        self._patterns = patterns
        self._current = current
        self._curriculum = curriculum

    def compose(self) -> ComposeResult:
        with Vertical(id="card"):
            yield Static("DSA Progress", classes="card-title")
            yield Static("", classes="card-rule")
            with VerticalScroll(id="card-scroll"):
                for p in self._patterns:
                    yield Static(display_pattern(p.pattern), classes="card-title")
                    if p.status == "mastered":
                        yield Static("✓ Mastered", classes="card-line ok")
                    elif self._current is not None and p.pattern == self._current.pattern:
                        yield Static("● In Progress", classes="card-line cur")
                    else:
                        yield Static("○ Not Started", classes="card-line todo")
                    if p.attempts:
                        yield Static(
                            f"Attempts        {p.attempts}\n"
                            f"Correct streak {p.correct_streak}\n"
                            f"Difficulty     {p.difficulty.value.title()}",
                            classes="card-line",
                        )
                    yield Static("", classes="card-rule")
            yield Static("Curriculum", classes="card-title")
            for pattern in self._curriculum:
                name = display_pattern(pattern)
                matched = next((p for p in self._patterns if p.pattern == pattern), None)
                if matched and matched.status == "mastered":
                    marker = "✓"
                elif self._current is not None and self._current.pattern == pattern:
                    marker = "→"
                else:
                    marker = "○"
                yield Static(f"{marker} {name}", classes="card-line muted")


class HelpScreen(ModalScreen[None]):
    """Command and key reference (spec §20)."""

    BINDINGS = [Binding("escape", "close", "close")]

    def action_close(self) -> None:
        self.app.pop_screen()

    def compose(self) -> ComposeResult:
        with Vertical(id="card"):
            yield Static("open-dsa commands", classes="card-title")
            yield Static(
                "/skip      skip the current question (no credit)\n"
                "/next      advance manually (same as /skip)\n"
                "/resolve   force a verdict during a follow-up\n"
                "/panel     toggle the progress sidebar\n"
                "/progress  show the progress screen\n"
                "/history   show the progress screen\n"
                "/help      show this help\n"
                "/quit      end the session",
                classes="card-line",
            )
            yield Static("", classes="card-rule")
            yield Static("Keys", classes="card-title")
            yield Static(
                "Enter         submit your answer\n"
                "Tab             move focus\n"
                "Esc             close overlays\n"
                "PageUp/PageDown scroll\n"
                "Ctrl+C          quit",
                classes="card-line",
            )


class ErrorScreen(ModalScreen[None]):
    """Gemini/API failure, session preserved (spec §19)."""

    BINDINGS = [Binding("escape", "retry", "retry")]

    def __init__(
        self,
        detail: str,
        on_retry: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        super().__init__()
        self._detail = detail
        self._on_retry = on_retry
        self._on_quit = on_quit

    def action_retry(self) -> None:
        self._on_retry()

    def compose(self) -> ComposeResult:
        with Vertical(id="card"):
            yield Static("Could not generate the next question.", classes="card-title")
            yield Static("The session has been preserved.", classes="card-sub")
            if self._detail:
                yield Static(self._detail, id="error-detail")
            with Horizontal():
                yield Button("Retry", variant="primary")
                yield Button("Quit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.label is not None and "Retry" in str(event.button.label):
            self._on_retry()
        else:
            self._on_quit()