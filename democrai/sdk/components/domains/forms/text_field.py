from typing import List, Dict, Any, Optional
from democrai.sdk.components.base import Component

class TextField(Component):
    """Single-line text input component."""
    type = "TextField"

    def __init__(
        self,
        id: str,
        label: str = "",
        value: str = "",
        placeholder: str = "",
        password: bool = False,
    ):
        super().__init__(id)
        self.mutable_value("value").interactive()
        self.set_prop("label", {"literalString": label})
        self.set_prop("value", value)
        self.set_prop("placeholder", placeholder)
        self.set_prop("password", password)
