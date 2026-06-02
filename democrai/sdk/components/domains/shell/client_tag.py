from typing import Any
from democrai.sdk.components.base import Component

class ClientTag(Component):
    """Placeholder resolved by the client into concrete UI components."""

    type = "ClientTag"

    def __init__(self, id: str, tag: Any):
        super().__init__(id)
        
        if hasattr(tag, "to_dict"):
            self.set_prop("tag", tag)
        else:
            self.set_prop("tag", str(tag))
