from typing import Dict, Any, Optional
from democrai.sdk.components.base import Component


class Title(Component):
    """Heading component with configurable semantic level."""

    type = "Title"

    def __init__(self, id: str, text: str, level: int = 3):
        super().__init__(id)
        # Gestione Binding (A2UI Contract)
        if isinstance(text, dict) and (
            text.get("type") in {"store", "data", "action", "literal"}
            or "path" in text
        ):
            self.set_prop("text", text)
        elif hasattr(text, "to_dict"):
            self.set_prop("text", text)
        else:
            # Fallback per stringhe semplici o altri tipi letterali
            self.set_prop("text", {"literalString": str(text)})
        self.set_prop("level", level)
