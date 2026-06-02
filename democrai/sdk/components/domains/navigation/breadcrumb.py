from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component

class Breadcrumb(Component):
    """Breadcrumb navigation component for hierarchical route context."""
    type = "Breadcrumb"

    def __init__(self, id: str, segments: Optional[List[Dict[str, Any]]] = None, separator: str = "/"):
        super().__init__(id)
        self.set_prop("segments", segments if segments is not None else [])
        self.set_prop("separator", separator)
