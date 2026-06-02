from typing import Any
from democrai.sdk.components.base import Component

class Markdown(Component):
    """Markdown-rendered text block component."""
    type = "Markdown"

    def __init__(self, id: str, text: Any):
        super().__init__(id)
        self.mutable_text("text")
        if isinstance(text, dict) and (
            text.get("type") in {"store", "data", "action", "literal"}
            or "path" in text
        ):
            self.set_prop("text", text)
        elif hasattr(text, "to_dict"):
            self.set_prop("text", text)
        else:
            self.set_prop("text", {"literalString": str(text)})
