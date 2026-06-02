from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class ScrollToBottomButton(Component):
    """Utility button that returns the conversation viewport to the latest content."""
    type = "ScrollToBottomButton"

    def __init__(self, id: str, label: str = "Jump to latest", action: Optional[Any] = None, params: Optional[dict] = None):
        super().__init__(id)
        self.set_prop("label", {"literalString": label})
        if action:
            if isinstance(action, dict):
                self.set_prop("action", action)
            else:
                self.set_action(str(action), params)
