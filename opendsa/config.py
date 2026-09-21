"""Typed loader for the single config.toml.

No magic numbers live in logic — every threshold is read here and exposed
through frozen dataclasses.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

VALID_DIFFICULTIES = {"easy", "medium", "hard"}

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.toml"


@dataclass(frozen=True, slots=True)
class AppSettings:
    database_path: Path
    default_model: str


@dataclass(frozen=True, slots=True)
class ContextSettings:
    last_n_turns: int
    compaction_threshold_percent: int


@dataclass(frozen=True, slots=True)
class ModelSettings:
    provider: str
    context_window_tokens: int


@dataclass(frozen=True, slots=True)
class DoubtSettings:
    loop_cap: int


@dataclass(frozen=True, slots=True)
class MasterySettings:
    min_attempts: int
    min_correct_streak: int


@dataclass(frozen=True, slots=True)
class DifficultySettings:
    start: str
    floor: str


@dataclass(frozen=True, slots=True)
class BankSettings:
    path: Path


@dataclass(frozen=True, slots=True)
class FlavorSettings:
    companies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Config:
    app: AppSettings
    context: ContextSettings
    model: ModelSettings
    doubts: DoubtSettings
    mastery: MasterySettings
    difficulty: DifficultySettings
    bank: BankSettings
    flavor: FlavorSettings
    curriculum: tuple[str, ...]


def _require(raw: dict[str, Any], section: str, key: str) -> Any:
    if section not in raw or key not in raw[section]:
        raise ValueError(f"config.toml is missing required value [{section}].{key}")
    return raw[section][key]


def _positive_int(value: Any, section: str, key: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"[{section}].{key} must be a positive integer, got {value!r}")
    return value


def _difficulty(value: Any, section: str, key: str) -> str:
    if not isinstance(value, str) or value not in VALID_DIFFICULTIES:
        raise ValueError(
            f"[{section}].{key} must be one of {sorted(VALID_DIFFICULTIES)}, got {value!r}"
        )
    return value


def _resolve_home(path: str) -> Path:
    expanded = os.path.expanduser(path)
    return Path(expanded).expanduser().absolute()


def _build(data: dict[str, Any]) -> Config:
    difficulty = DifficultySettings(
        start=_difficulty(_require(data, "difficulty", "start"), "difficulty", "start"),
        floor=_difficulty(_require(data, "difficulty", "floor"), "difficulty", "floor"),
    )
    if difficulty.floor == "hard":
        raise ValueError("[difficulty].floor must not be 'hard' in v1 (floor is Easy by design)")

    compaction = _positive_int(
        _require(data, "context", "compaction_threshold_percent"),
        "context",
        "compaction_threshold_percent",
    )
    if compaction > 100:
        raise ValueError("[context].compaction_threshold_percent must be between 1 and 100")

    curriculum = _require(data, "curriculum", "patterns")
    if (
        not isinstance(curriculum, list)
        or not curriculum
        or any(not isinstance(p, str) or not p for p in curriculum)
    ):
        raise ValueError("[curriculum].patterns must be a non-empty list of strings")

    companies = _require(data, "flavor", "companies")
    if (
        not isinstance(companies, list)
        or not companies
        or any(not isinstance(c, str) or not c for c in companies)
    ):
        raise ValueError("[flavor].companies must be a non-empty list of strings")

    return Config(
        app=AppSettings(
            database_path=_resolve_home(str(_require(data, "app", "database_path"))),
            default_model=str(_require(data, "app", "default_model")),
        ),
        context=ContextSettings(
            last_n_turns=_positive_int(_require(data, "context", "last_n_turns"), "context", "last_n_turns"),
            compaction_threshold_percent=compaction,
        ),
        model=ModelSettings(
            provider=str(_require(data, "model", "provider")),
            context_window_tokens=_positive_int(
                _require(data, "model", "context_window_tokens"), "model", "context_window_tokens"
            ),
        ),
        doubts=DoubtSettings(
            loop_cap=_positive_int(_require(data, "doubts", "loop_cap"), "doubts", "loop_cap")
        ),
        mastery=MasterySettings(
            min_attempts=_positive_int(
                _require(data, "mastery", "min_attempts"), "mastery", "min_attempts"
            ),
            min_correct_streak=_positive_int(
                _require(data, "mastery", "min_correct_streak"), "mastery", "min_correct_streak"
            ),
        ),
        difficulty=difficulty,
        bank=BankSettings(path=Path(str(_require(data, "bank", "path")))),
        flavor=FlavorSettings(companies=tuple(companies)),
        curriculum=tuple(curriculum),
    )


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Load config.toml into a validated Config. Raises on any bad value."""
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not cfg_path.is_file():
        raise FileNotFoundError(f"config file not found: {cfg_path}")
    with cfg_path.open("rb") as fh:
        data = tomllib.load(fh)
    return _build(data)


def config_fields() -> tuple[str, ...]:
    return tuple(f.name for f in fields(Config))