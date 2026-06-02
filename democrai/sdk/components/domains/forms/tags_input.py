from typing import Any, Optional

from democrai.sdk.components.base import Component


class TagsInput(Component):
    """Compact chip/tag editor for list values."""

    type = "TagsInput"

    def __init__(
        self,
        id: str,
        label: str = "",
        value: Optional[list[Any]] = None,
        placeholder: str = "",
        add_label: str = "Add",
        item_schema: Optional[dict[str, Any]] = None,
        action: Any = None,
        params: Optional[dict[str, Any]] = None,
    ):
        super().__init__(id)
        self.mutable_value("value").interactive()
        self.set_prop("label", {"literalString": label})
        self.set_prop("value", value if value is not None else [])
        self.set_prop("placeholder", placeholder)
        self.set_prop("add_label", {"literalString": add_label})
        if item_schema is None:
            raise ValueError("TagsInput item_schema is required")
        self.set_prop("item_schema", item_schema)
        if params is not None:
            self.set_prop("params", params)
        if action:
            if isinstance(action, dict):
                self.set_prop("action", action)
            else:
                self.set_action(str(action), params)
