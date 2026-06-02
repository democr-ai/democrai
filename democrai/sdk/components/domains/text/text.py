from typing import Dict, Any, Optional
from democrai.sdk.components.base import Component

class Text(Component):
    """Plain text component supporting literal and bound-value payloads."""
    type = "Text"

    def __init__(self, id: str, text: Any):
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
