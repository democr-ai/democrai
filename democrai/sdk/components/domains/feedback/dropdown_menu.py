from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component

class DropdownMenu(Component):
    """Dropdown menu component for contextual or secondary actions."""
    type = "DropdownMenu"

    def __init__(self, id: str, label: str, items: Optional[List[Dict[str, Any]]] = None, variant: str = "default"):
        super().__init__(id)
        self.mutable_collection("items").interactive()
        self.set_prop("label", {"literalString": label})
        self.set_prop("items", items if items is not None else [])
        self.set_prop("variant", variant)
