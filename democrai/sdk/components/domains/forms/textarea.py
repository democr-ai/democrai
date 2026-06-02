from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component

class TextArea(Component):
    """Multi-line text input component."""
    type = "TextArea"

    def __init__(
        self,
        id: str,
        label: str = "",
        value: str = "",
        placeholder: str = "",
        auto_resize: bool = True,
        disabled: bool = False,
        rows: int = 3,
    ):
        super().__init__(id)
        self.mutable_value("value").allow("disabled.set").interactive()
        self.set_prop("label", {"literalString": label})
        self.set_prop("value", value)
        self.set_prop("placeholder", placeholder)
        self.set_prop("auto_resize", auto_resize)
        self.set_prop("disabled", disabled)
        self.set_prop("rows", rows)
