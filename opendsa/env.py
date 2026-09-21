"""Minimal .env loader (no external dependency).

Reads KEY=VALUE lines from a .env file, ignoring comments and blanks,
honouring an optional ``export`` prefix, stripping quotes, and never
overriding variables that already exist in the environment.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def find_dotenv(name: str = ".env") -> Path | None:
    """Locate the nearest .env: cwd, walking up, then the project root."""
    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])
    for extra in (Path(__file__).resolve().parents[1],):
        if extra not in candidates:
            candidates.append(extra)

    seen: set[Path] = set()
    for base in candidates:
        if base in seen:
            continue
        seen.add(base)
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def load_dotenv(path: str | Path | None = None) -> bool:
    """Load the .env into os.environ (unless already set). True if a file loaded."""
    target = Path(path) if path is not None else find_dotenv()
    if target is None or not target.is_file():
        return False

    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE.match(line)
        if match is None:
            continue
        key, value = match.group(1), match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value
    return True