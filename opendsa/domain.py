"""Core enums and value objects. No storage or IO here."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Difficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Verdict(Enum):
    CORRECT = "correct"
    PARTIAL = "partial"
    WRONG = "wrong"
    SKIP = "skip"


_DECREMENT = [Difficulty.HARD, Difficulty.MEDIUM, Difficulty.EASY]
_INCREMENT = [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD]


def drop_one(difficulty: Difficulty) -> Difficulty:
    """One tier down, floored at Easy."""
    index = _DECREMENT.index(difficulty)
    return _DECREMENT[min(index + 1, len(_DECREMENT) - 1)]


def raise_one(difficulty: Difficulty) -> Difficulty:
    """One tier up, capped at Hard (unused in v1, kept for symmetry)."""
    index = _INCREMENT.index(difficulty)
    return _INCREMENT[min(index + 1, len(_INCREMENT) - 1)]


def difficulty_from(value: str) -> Difficulty:
    return Difficulty(value.lower())


def verdict_from(value: str) -> Verdict:
    return Verdict(value.strip().lower())


@dataclass(frozen=True, slots=True)
class Question:
    pattern: str
    difficulty: Difficulty
    company: str | None
    problem_number: int
    story: str
    title: str = ""

    @property
    def question_id(self) -> str:
        return f"lc-{self.problem_number}"


_DISPLAY_PATTERNS = {
    "two_pointer": "Two Pointer",
    "sliding_window": "Sliding Window",
    "binary_search": "Binary Search",
    "fast_slow_pointer": "Fast & Slow Pointer",
    "bfs_dfs": "BFS / DFS",
    "backtracking": "Backtracking",
    "dynamic_programming": "Dynamic Programming",
    "greedy": "Greedy",
}


def display_pattern(pattern: str) -> str:
    return _DISPLAY_PATTERNS.get(pattern, pattern.replace("_", " ").title())


@dataclass(frozen=True, slots=True)
class ProgressPattern:
    pattern: str
    position: int
    status: str
    difficulty: Difficulty
    attempts: int
    correct_streak: int
    wrong_streak: int
    mastered_at: str | None