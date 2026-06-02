from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component

class Accordion(Component):
    """Accordion component containing multiple collapsible items."""
    type = "Accordion"

    def __init__(self, id: str, items: Optional[List[Dict[str, Any]]] = None, multiple: bool = False, collapsible: bool = True):
        super().__init__(id)
        self.set_prop("items", items if items is not None else [])
        self.set_prop("multiple", multiple)
        self.set_prop("collapsible", collapsible)
