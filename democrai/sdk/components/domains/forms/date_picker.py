from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component

class DatePicker(Component):
    """Single-date picker input component."""
    type = "DatePicker"

    def __init__(
        self,
        id: str,
        label: str = "",
        value: str = "",
        min_date: str = "",
        max_date: str = "",
        max_width: Optional[int] = None,
        action: Optional[str] = None,
        params: Optional[dict] = None,
        format: str = "yyyy-MM-dd",
    ):
        super().__init__(id)
        self.mutable_value("value").interactive()
        self.set_prop("label", {"literalString": label})
        self.set_prop("value", value)
        self.set_prop("min_date", min_date)
        self.set_prop("max_date", max_date)
        self.set_prop("max_width", max_width)
        self.set_prop("format", format)
        if action:
            self.set_action(action, params)
