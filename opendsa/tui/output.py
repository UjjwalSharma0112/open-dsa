"""Bridge from the controller thread into the Textual app (the Output impl).

Every controller event is forwarded onto the app thread with
``call_from_thread`` so widgets are only ever touched on the UI thread.
``ask`` blocks the controller thread on a queue until the app delivers a
submitted answer.
"""

from __future__ import annotations

from queue import Queue
from typing import TYPE_CHECKING, Callable

from ..domain import Question

if TYPE_CHECKING:
    from .app import StudyApp


class UIOutput:
    def __init__(self, app: "StudyApp") -> None:
        self._app = app
        self._pending: Queue[str] = Queue()

    # -- Output protocol ----------------------------------------------------

    def question(self, index: int, question: Question) -> None:
        self._call(self._app.render_question, index, question)

    def state(self, name: str) -> None:
        self._call(self._app.set_state, name)

    def user(self, text: str) -> None:
        self._call(self._app.convo_user, text)

    def assistant(self, text: str) -> None:
        self._call(self._app.convo_assistant, text)

    def stream(self, chunk: str) -> None:
        self._call(self._app.convo_stream, chunk)

    def stream_end(self) -> None:
        self._call(self._app.convo_stream_end)

    def followup(self, text: str, used: int, cap: int) -> None:
        self._call(self._app.convo_followup, text, used, cap)

    def verdict(self, label: str) -> None:
        self._call(self._app.convo_verdict, label)

    def note(self, text: str) -> None:
        self._call(self._app.convo_note, text)

    def link(self, number: int) -> None:
        self._call(self._app.convo_link, number)

    def ask(self, prompt: str) -> str:
        self._call(self._app.demand, prompt)
        return self._pending.get()

    # -- app -> controller --------------------------------------------------

    def deliver(self, value: str) -> None:
        self._pending.put(value)

    # -- plumbing -----------------------------------------------------------

    def _call(self, fn: Callable[..., None], *args) -> None:
        self._app.call_from_thread(fn, *args)