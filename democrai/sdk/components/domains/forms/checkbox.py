from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component

class Checkbox(Component):
    """Boolean form input rendered as a checkbox."""
    type = "Checkbox"

    def __init__(self, id: str, label: str, checked: bool = False, action: Optional[str] = None, params: Optional[dict] = None):
        super().__init__(id)
        self.allow("checked.set").interactive()
        self.set_prop("label", {"literalString": label})
        self.set_prop("checked", checked)
        if action:
            self.set_action(action, params)
