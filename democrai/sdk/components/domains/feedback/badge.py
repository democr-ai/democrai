from __future__ import annotations
from typing import Any
from democrai.sdk.components.base import Component


class Badge(Component):
    """Compact badge component for status, tags, and counters."""

    type = "Badge"

    def __init__(self, id: str, text: Any, variant: Any = "default"):
        super().__init__(id)
        self.mutable_text("text").allow("variant.set").interactive()
        self._apply_bindable_text(text)
        self._apply_bindable_variant(variant)

    def _apply_bindable_text(self, value: Any) -> None:
        if isinstance(value, dict) and (
            value.get("type") in {"store", "data", "action", "literal"}
            or "path" in value
        ):
            self.set_prop("text", value)
            return
        if hasattr(value, "to_dict"):
            self.set_prop("text", value)
            return
        self.set_prop("text", {"literalString": "" if value is None else str(value)})

    def _apply_bindable_variant(self, value: Any) -> None:
        if isinstance(value, dict) and (
            value.get("type") in {"store", "data", "action", "literal"}
            or "path" in value
        ):
            self.set_prop("variant", value)
            return
        if hasattr(value, "to_dict"):
            self.set_prop("variant", value)
            return
        self.set_prop("variant", "default" if value is None else str(value))
