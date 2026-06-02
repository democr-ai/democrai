from typing import List, Dict, Any, Optional
from democrai.sdk.components.base import Component

class FolderSelector(Component):
    """Filesystem folder selection input component."""
    type = "FolderSelector"

    def __init__(self, id: str, label: str, value: str = "", placeholder: str = ""):
        super().__init__(id)
        self.mutable_value("value").interactive()
        self.set_prop("label", label)
        self.set_prop("value", value)
        self.set_prop("placeholder", placeholder)
