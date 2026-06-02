from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class MessageList(Component):
    """Conversation message collection component."""
    type = "MessageList"

    def __init__(self, id: str, messages: Optional[List[Dict[str, Any]]] = None):
        super().__init__(id)
        self.mutable_collection("messages").interactive()
        self.set_prop("messages", messages if messages is not None else [])
