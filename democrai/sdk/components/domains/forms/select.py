from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component

class Select(Component):
    """Select input supporting static or runtime-provided options."""
    type = "Select"

    def __init__(
        self,
        id: str,
        label: str = "",
        options: Optional[List[Dict[str, Any]]] = None,
        value: Any = "",
        placeholder: str = "",
        multiple: bool = False,
        searchable: bool = False,
        max_width: Optional[int] = None,
        action: Optional[str] = None,
        params: Optional[dict] = None,
        options_action: Optional[str] = None,
        options_store: Optional[str] = None,
        options_plain: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__(id)
        self.mutable_value("value").mutable_collection("options").interactive()
        self.set_prop("label", {"literalString": label})
        resolved_options = options if options is not None else options_plain
        self.set_prop("options", resolved_options if resolved_options is not None else [])
        self.set_prop("value", value)
        self.set_prop("placeholder", placeholder)
        self.set_prop("multiple", multiple)
        self.set_prop("searchable", searchable)
        self.set_prop("max_width", max_width)
        if options_action:
            self.set_prop("optionsAction", {"name": options_action, "context": {}})
        if options_store:
            self.set_prop("optionsStore", options_store)
        if action:
            self.set_action(action, params)
