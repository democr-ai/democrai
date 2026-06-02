from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class Suggestions(Component):
    """Suggested prompts or actions for a conversation surface."""
    type = "Suggestions"

    def __init__(self, id: str, suggestions: Optional[List[Dict[str, Any]]] = None, action: Optional[Any] = None, params: Optional[dict] = None):
        super().__init__(id)
        self.mutable_collection("suggestions").interactive()
        self.set_prop("suggestions", suggestions if suggestions is not None else [])
        if action:
            if isinstance(action, dict):
                self.set_prop("action", action)
            else:
                self.set_action(str(action), params)
