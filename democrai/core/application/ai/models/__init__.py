from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "HardwareValidator",
    "engine_model_source_modes",
    "get_engine_model",
    "list_engine_models",
    "resolve_engine_model",
]


if TYPE_CHECKING:
    from .catalog import (
        engine_model_source_modes,
        get_engine_model,
        list_engine_models,
        resolve_engine_model,
    )
    from .hardware_compatibility import HardwareValidator


def __getattr__(name: str) -> Any:
    if name == "HardwareValidator":
        return import_module(".hardware_compatibility", __name__).HardwareValidator
    if name in {
        "engine_model_source_modes",
        "get_engine_model",
        "list_engine_models",
        "resolve_engine_model",
    }:
        return getattr(import_module(".catalog", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
