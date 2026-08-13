"""Language registry.

One adapter per language, looked up by code. The app drills a single language
today, so ``DEFAULT_LANGUAGE`` is what everything reaches for — but callers go
through ``get_adapter()`` rather than importing ``pt_pt`` directly, so adding a
second language is a registration rather than a change to every call site.
"""

from __future__ import annotations

from .base import (
    Cell,
    LanguageAdapter,
    NotAVerb,
    Paradigm,
    SourceUnavailable,
    UnknownWord,
)
from .pt_pt import CODE as PT_PT
from .pt_pt import PortugueseAdapter

DEFAULT_LANGUAGE = PT_PT

_ADAPTERS: dict[str, LanguageAdapter] = {
    PT_PT: PortugueseAdapter(),
}


def get_adapter(code: str | None = None) -> LanguageAdapter:
    """The adapter for a language code, defaulting to the drilled language."""
    adapter = _ADAPTERS.get(code or DEFAULT_LANGUAGE)
    if adapter is None:
        raise KeyError(f"no adapter for language {code!r}")
    return adapter


def languages() -> list[str]:
    return sorted(_ADAPTERS)


__all__ = [
    "Cell",
    "DEFAULT_LANGUAGE",
    "LanguageAdapter",
    "NotAVerb",
    "Paradigm",
    "SourceUnavailable",
    "UnknownWord",
    "get_adapter",
    "languages",
]
