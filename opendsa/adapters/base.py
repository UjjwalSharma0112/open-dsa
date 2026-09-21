"""The single model interface every provider implements (guidelines.md §2.2).

Conversation history is a list of dicts::

    {"role": "user" | "assistant", "content": str}

Adapters own provider-specific wire formatting. Business logic builds
``system`` + ``history`` and reads back the returned text.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class ModelAdapter(Protocol):
    def generate(self, system: str, history: list[dict]) -> str: ...

    def stream(self, system: str, history: list[dict]) -> Iterator[str]: ...