from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "engine",
    "models",
    "model_orchestrator",
]


def __getattr__(name: str) -> Any:
    if name == "engine":
        return import_module(".engine", __name__)
    if name == "models":
        return import_module(".models", __name__)
    if name == "model_orchestrator":
        return import_module(".orchestrator", __name__).model_orchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
