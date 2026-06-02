from typing import List, Dict, Any, Optional
from democrai.sdk.components.base import Component

class RadioGroup(Component):
    """Single-choice input rendered as a radio group."""
    type = "RadioGroup"

    def __init__(
        self,
        id: str,
        label: str,
        options: Optional[List[Dict[str, Any]]] = None,
        value: str = "",
        options_action: Optional[str] = None,
        options_store: Optional[str] = None,
    ):
        super().__init__(id)
        self.mutable_value("value").mutable_collection("options").interactive()
        self.set_prop("label", {"literalString": label})
        self.set_prop("options", options if options is not None else [])
        self.set_prop("value", value)
        if options_action:
            self.set_prop("optionsAction", {"name": options_action, "context": {}})
        if options_store:
            self.set_prop("optionsStore", options_store)
