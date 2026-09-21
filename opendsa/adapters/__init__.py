"""Model adapter package.

Rule (guidelines.md §2.2): business logic never imports a provider SDK.
Everything talks to ``ModelAdapter``; the factory here maps a provider name
to a concrete adapter.
"""

from __future__ import annotations

from .base import ModelAdapter

__all__ = ["ModelAdapter", "get_adapter", "list_providers"]


def get_adapter(provider: str, model: str) -> ModelAdapter:
    """Build the adapter for a provider. Import of the provider module is
    deferred so importing this package never pulls a provider SDK in."""
    if provider == "gemini":
        from .gemini import GeminiAdapter

        return GeminiAdapter(model=model)
    raise ValueError(
        f"unknown model provider {provider!r}; known providers: {list_providers()}"
    )


def list_providers() -> tuple[str, ...]:
    return ("gemini",)