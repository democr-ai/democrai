from __future__ import annotations

from typing import Callable

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.application.models.context import CoreModelContext


_CORE_MODEL_REGISTRY: dict[str, Callable[[CoreModelContext], BaseCoreModel]] = {}


def register_core_model(
    name: str, factory: Callable[[CoreModelContext], BaseCoreModel]
) -> None:
    normalized_name = name.strip().lower()
    if not normalized_name:
        raise ValueError("core model name cannot be empty")
    _CORE_MODEL_REGISTRY[normalized_name] = factory


def build_core_model(name: str, ctx: CoreModelContext) -> BaseCoreModel:
    normalized_name = name.strip().lower()
    if normalized_name not in _CORE_MODEL_REGISTRY:
        raise KeyError(f"Unknown core model: {name}")
    return _CORE_MODEL_REGISTRY[normalized_name](ctx)


def list_core_models() -> list[str]:
    return sorted(_CORE_MODEL_REGISTRY.keys())
