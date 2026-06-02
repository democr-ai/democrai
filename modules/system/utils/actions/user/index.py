from __future__ import annotations

from typing import Any


def build_aux_surface_messages(module_sdk, builder, surface_id: str) -> list[dict]:
    return module_sdk.effects.build_aux_surface_messages(builder, surface_id)


def t(module_sdk, key: str, *, context: dict[str, Any] | None = None) -> str:
    return module_sdk.i18n.t(key, context=context or {})
