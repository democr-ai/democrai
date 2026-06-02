from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "genai_manager",
    "get_provider_definition",
    "list_provider_definitions",
    "Message",
    "ContentPart",
    "ContentType",
    "CompletionOptions",
    "MessageRole",
]


if TYPE_CHECKING:
    from .manifests import get_provider_definition, list_provider_definitions
    from .provider_manager import genai_manager
    from .schemas.completion import (
        CompletionOptions,
        ContentPart,
        ContentType,
        Message,
        MessageRole,
    )


def __getattr__(name: str) -> Any:
    if name == "genai_manager":
        return import_module(".provider_manager", __name__).genai_manager
    if name in {"get_provider_definition", "list_provider_definitions"}:
        return getattr(import_module(".manifests", __name__), name)
    if name in {
        "Message",
        "ContentPart",
        "ContentType",
        "CompletionOptions",
        "MessageRole",
    }:
        return getattr(import_module(".schemas.completion", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
