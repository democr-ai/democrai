from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component

class Attachment(Component):
    """Attachment input component for one or more uploaded files."""
    type = "Attachment"

    def __init__(
        self,
        id: str,
        label: str = "",
        accept: str = "",
        multiple: bool = False,
        value: Optional[List[Dict[str, Any]]] = None,
        action: Optional[str] = None,
        params: Optional[dict] = None,
        ingest: bool = True,
    ):
        super().__init__(id)
        self.mutable_collection("value").interactive()
        self.set_prop("label", {"literalString": label})
        self.set_prop("accept", accept)
        self.set_prop("multiple", multiple)
        self.set_prop("ingest", ingest)
        self.set_prop("value", value if value is not None else [])
        if action:
            self.set_action(action, params)
