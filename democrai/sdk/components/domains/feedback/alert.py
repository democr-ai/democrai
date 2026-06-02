from __future__ import annotations
from typing import Any
from democrai.sdk.components.base import Component


class Alert(Component):
    """Alert banner component for info, warning, success, or error messages."""

    type = "Alert"

    def __init__(
        self,
        id: str,
        title: Any,
        description: Any = "",
        variant: Any = "info",
    ):
        super().__init__(id)
        self.allow("title.set", "description.set", "variant.set").interactive()
        self._apply_bindable_text("title", title)
        self._apply_bindable_text("description", description)
        self._apply_bindable_variant(variant)

    def _apply_bindable_text(self, name: str, value: Any) -> None:
        if isinstance(value, dict) and (
            value.get("type") in {"store", "data", "action", "literal"}
            or "path" in value
        ):
            self.set_prop(name, value)
            return
        if hasattr(value, "to_dict"):
            self.set_prop(name, value)
            return
        self.set_prop(name, {"literalString": "" if value is None else str(value)})

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
        self.set_prop("variant", "info" if value is None else str(value))
