"""Small reusable widgets: header, status bar, conversation stream.

Kept inside the TUI package on purpose — none of this is business logic.
"""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Markdown, Static, TextArea

STATUS_DEFAULT = "Enter submit • /skip skip • /next next • /help commands"


class AnswerBox(TextArea):
    """Answer input that submits on Enter (TextArea's default key inserts a
    newline, so we override it here; Ctrl+Enter still works as a fallback)."""

    BINDINGS = [Binding("enter", "submit", "Submit", priority=True)]

    def action_submit(self) -> None:
        self.app.action_submit()


class HeaderBar(Horizontal):
    """Persistent top bar: brand left, session context right (spec §3)."""

    def __init__(self, brand: str = "open-dsa", hint: str = "") -> None:
        super().__init__(id="header")
        self._brand = brand
        self._hint = hint

    def compose(self) -> None:
        yield Static(self._brand, id="brand")
        yield Static(self._hint, id="hint")

    def set_hint(self, text: str) -> None:
        self.query_one("#hint", Static).update(text)


class StatusBar(Horizontal):
    """One-line command/state footer (spec §6), opencode-style.

    Shows a small animated spinner in place of any blocking modal while the
    controller is waiting on the model.
    """

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, text: str = STATUS_DEFAULT) -> None:
        super().__init__(id="status")
        self._default = text
        self._busy_text = ""
        self._phase = 0
        self._timer = None

    def compose(self) -> None:
        yield Static("", id="status-text")

    def on_mount(self) -> None:
        self.query_one("#status-text", Static).update(self._default)

    def set(self, text: str) -> None:
        self._stop_busy()
        self.query_one("#status-text", Static).update(text)

    def busy(self, message: str) -> None:
        self._stop_busy()
        self._busy_text = message
        self.add_class("busy")
        self._update_spinner()
        self._timer = self.set_interval(0.1, self._tick)

    def idle(self) -> None:
        self._stop_busy()
        self.remove_class("busy")
        self.query_one("#status-text", Static).update(self._default)

    def _tick(self) -> None:
        self._phase = (self._phase + 1) % len(self._FRAMES)
        self._update_spinner()

    def _update_spinner(self) -> None:
        self.query_one("#status-text", Static).update(
            f"{self._FRAMES[self._phase]} {self._busy_text}"
        )

    def _stop_busy(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None


class Conversation(VerticalScroll):
    """One scrollable study view, opencode-style: a running log of every
    question and exchange. Each question appends below the last one, and
    earlier questions stay readable by scrolling up — nothing is wiped when
    the next question arrives.

    Supports optional live streaming: chunks are appended to the in-progress
    assistant turn until ``end_stream`` is called.
    """

    def __init__(self) -> None:
        super().__init__(id="convo")
        self._stream_content: Static | None = None
        self._stream_text = ""
        self._last_assistant_streamed = False

    # -- lifecycle ---------------------------------------------------------

    def _append_turn(self, role: str, content: Static) -> None:
        turn = Vertical(
            Static(role, classes="turn-role"),
            content,
            classes="turn",
        )
        self.mount(turn)

    def _settle(self) -> None:
        self._last_assistant_streamed = False
        self._scroll_end()

    def _scroll_end(self) -> None:
        self.scroll_end(animate=False)

    # -- turns -------------------------------------------------------------

    def add_question(self, heading: str, story: str) -> None:
        """Append a question block to the running log (opencode-style): past
        exchanges stay above and remain scrollable."""
        block = Vertical(
            Static(heading, classes="convo-qtitle"),
            Markdown(story, classes="convo-qbody"),
            classes="turn question",
        )
        self.mount(block)
        self._scroll_end()

    def add_user(self, text: str) -> None:
        self._append_turn("You", Static(text, classes="turn-content"))
        self._settle()

    def add_assistant(self, text: str) -> None:
        self._append_turn("open-dsa", Static(text, classes="turn-content"))
        self._settle()

    def begin_stream(self) -> None:
        self._stream_text = ""
        self._stream_content = Static("", classes="turn-content")
        self._append_turn("open-dsa", self._stream_content)
        self._last_assistant_streamed = True
        self._scroll_end()

    def stream(self, chunk: str) -> None:
        if self._stream_content is None:
            self.begin_stream()
        self._stream_text += chunk
        self._stream_content.update(self._stream_text)
        self._scroll_end()

    def end_stream(self) -> None:
        self._stream_content = None
        self._scroll_end()

    def add_followup(self, text: str, used: int, cap: int) -> None:
        if text and not self._last_assistant_streamed:
            self.add_assistant(text)
        self.mount(Static(f"Follow-up {used + 1} / {cap}", classes="turn-count"))
        self._settle()

    def add_verdict(self, label: str) -> None:
        kind = {"✓": "correct", "~": "partial", "×": "wrong"}.get(label[0], "partial")
        self.mount(Static(label, classes=f"turn-verdict-{kind}"))
        self._scroll_end()

    def add_note(self, text: str) -> None:
        self.mount(Static(f"· {text}", classes="turn-note"))
        self._scroll_end()

    def add_link(self, number: int) -> None:
        self.mount(Static(f"LeetCode #{number}", classes="turn-link"))
        self._scroll_end()