from typing import Any, Optional

from democrai.sdk.components.base import Component


class EditableList(Component):
    """Incremental editor for a list of string values."""

    type = "EditableList"

    def __init__(
        self,
        id: str,
        value: Optional[list[str]] = None,
        item_label: str = "",
        add_label: str = "Add",
        remove_label: str = "Remove",
        submit_label: str = "Save",
        placeholder: str = "",
        item_schema: Optional[dict[str, Any]] = None,
        action: Any = None,
        params: Optional[dict[str, Any]] = None,
        track_loading: Optional[str | list[str] | tuple[str, ...]] = None,
    ):
        super().__init__(id)
        self.mutable_value("value").interactive()
        self.set_prop("value", value if value is not None else [])
        self.set_prop("item_label", {"literalString": item_label})
        self.set_prop("add_label", {"literalString": add_label})
        self.set_prop("remove_label", {"literalString": remove_label})
        self.set_prop("submit_label", {"literalString": submit_label})
        self.set_prop("placeholder", placeholder)
        if item_schema is None:
            raise ValueError("EditableList item_schema is required")
        self.set_prop("item_schema", item_schema)
        if params is not None:
            self.set_prop("params", params)
        if track_loading:
            if isinstance(track_loading, (list, tuple, set)):
                self.track_loading(*[str(item) for item in track_loading])
            else:
                self.track_loading(str(track_loading))
        if action:
            if isinstance(action, dict):
                self.set_prop("action", action)
            else:
                self.set_action(str(action), params)
