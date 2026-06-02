from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component

class Progress(Component):
    """Progress indicator component for numeric completion state."""
    type = "Progress"

    def __init__(self, id: str, value: int = 0, maximum: int = 100, label: str = "", show_label: bool = True):
        super().__init__(id)
        self.mutable_value("value").allow("maximum.set", "label.set").interactive()
        self.set_prop("value", value)
        self.set_prop("maximum", maximum)
        self.set_prop("label", {"literalString": label})
        self.set_prop("show_label", show_label)
