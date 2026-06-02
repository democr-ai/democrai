from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component

class Collapsible(Component):
    """Single collapsible content block with title and body content."""
    type = "Collapsible"

    def __init__(self, id: str, title: str, content: str = "", open: bool = False):
        super().__init__(id)
        self.set_prop("title", {"literalString": title})
        self.set_prop("content", {"literalString": content})
        self.set_prop("open", open)
