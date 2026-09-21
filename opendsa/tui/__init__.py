"""TUI package — the only place Textual is imported (guideline 3: logic must
run without Textual)."""

from .app import StudyApp

__all__ = ["StudyApp"]