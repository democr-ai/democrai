from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class MessageItem(Component):
    """Single conversational message with role, text, metadata, and actions."""
    type = "MessageItem"

    def __init__(
        self,
        id: str,
        role: str,
        text: str,
        meta: str = "",
        actions: Optional[List[Dict[str, Any]]] = None,
        reasoning: str = "",
    ):
        super().__init__(id)
        self.mutable_text("text").allow(
            "meta.set",
            "actions.set",
            "reasoning.set",
        ).interactive()
        self.set_prop("role", role)
        self.set_prop("text", {"literalString": text})
        self.set_prop("meta", {"literalString": meta})
        self.set_prop("actions", actions if actions is not None else [])
        self.set_prop("reasoning", {"literalString": reasoning})
