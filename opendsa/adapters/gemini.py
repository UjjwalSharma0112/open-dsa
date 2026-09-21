"""Gemini adapter (v1) — the only provider module in the codebase.

Business logic never imports a provider SDK (guidelines 2.2); google-genai is
imported lazily on first use so the rest of the app imports and tests without
it installed.

Model resolution order: $GEMINI_MODEL env var > adapter ``model`` arg > default.
API key: $GOOGLE_API_KEY env var or the ``api_key`` arg.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

DEFAULT_MODEL = "gemini-2.5-flash"
_ROLE_MAP = {"assistant": "model", "model": "model", "user": "user"}

_genai: Any = None
_types: Any = None
_clients: dict[str, Any] = {}


def _load_sdk() -> tuple[Any, Any]:
    global _genai, _types
    if _genai is None:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "google-genai is not installed. Install the extra: pip install '.[gemini]'"
            ) from exc
        _genai, _types = genai, types
    return _genai, _types


def _client(api_key: str) -> Any:
    if api_key not in _clients:
        genai, _ = _load_sdk()
        _clients[api_key] = genai.Client(api_key=api_key)
    return _clients[api_key]


def _contents(types: Any, history: list[dict]) -> list[Any]:
    return [
        types.Content(
            role=_ROLE_MAP.get(m.get("role", "user"), "user"),
            parts=[types.Part(text=m.get("content", ""))],
        )
        for m in history
    ]


def _text(response: Any) -> str:
    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError(f"empty response from model: {response}")
    return text


class GeminiAdapter:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = os.environ.get("GEMINI_MODEL") or model or DEFAULT_MODEL
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY")

    # -- ModelAdapter ---------------------------------------------------------

    def generate(self, system: str, history: list[dict]) -> str:
        if not self._api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Put it in a .env file at the project "
                "root, or export it in your shell, or pass api_key= to GeminiAdapter."
            )
        _, types = _load_sdk()
        response = _client(self._api_key).models.generate_content(
            model=self.model,
            contents=_contents(types, history),
            config={"system_instruction": system},
        )
        return _text(response)

    def stream(self, system: str, history: list[dict]) -> Iterator[str]:
        if not self._api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Put it in a .env file at the project "
                "root, or export it in your shell, or pass api_key= to GeminiAdapter."
            )
        _, types = _load_sdk()
        chunks = _client(self._api_key).models.generate_content_stream(
            model=self.model,
            contents=_contents(types, history),
            config={"system_instruction": system},
        )
        for chunk in chunks:
            text = getattr(chunk, "text", None)
            if text:
                yield text