from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component

class Skeleton(Component):
    """Loading placeholder component that mimics the future content structure."""
    type = "Skeleton"

    def __init__(self, id: str, lines: int = 3, widths: Optional[List[int]] = None, avatar: bool = False):
        super().__init__(id)
        self.set_prop("lines", lines)
        self.set_prop("widths", widths if widths is not None else [])
        self.set_prop("avatar", avatar)
