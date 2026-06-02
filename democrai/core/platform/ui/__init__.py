from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["RenderService"]


if TYPE_CHECKING:
    from .render_service import RenderService


def __getattr__(name: str) -> Any:
    if name == "RenderService":
        return import_module(".render_service", __name__).RenderService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
