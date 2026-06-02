from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class Composer(Component):
    """Conversation composer input for chat and LLM interaction flows."""
    type = "Composer"

    def __init__(self, id: str, placeholder: str = "", value: str = "", disabled: bool = False, multiline: bool = True, send_action: Optional[Any] = None, cancel_action: Optional[Any] = None, ingest: bool = True):
        super().__init__(id)
        self.mutable_value("value").allow(
            "disabled.set",
            "model.set",
            "capabilities.set",
            "active_capabilities.set",
        ).interactive()
        self.set_prop("placeholder", placeholder)
        self.set_prop("value", value)
        self.set_prop("disabled", disabled)
        self.set_prop("multiline", multiline)
        self.set_prop("ingest", ingest)
        if send_action:
            self.set_prop(
                "send_action",
                send_action if isinstance(send_action, dict) else {"name": send_action, "context": {}},
            )
        if cancel_action:
            self.set_prop(
                "cancel_action",
                cancel_action if isinstance(cancel_action, dict) else {"name": cancel_action, "context": {}},
            )
