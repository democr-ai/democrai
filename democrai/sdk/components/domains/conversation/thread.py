from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class Thread(Container):
    """Conversation container that groups messages and chat controls."""
    type = "Thread"

    def __init__(self, id: str, children: Optional[List[Any]] = None, auto_scroll: bool = True):
        super().__init__(id, children)
        self.set_prop("auto_scroll", auto_scroll)
