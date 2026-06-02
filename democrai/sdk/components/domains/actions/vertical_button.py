from typing import Dict, Any, Optional
from democrai.sdk.components.base import Component

class VerticalButton(Component):
    """Button variant intended for icon-over-label vertical layouts."""
    type = "VerticalButton"

    def __init__(
        self,
        id: str,
        label: str,
        action: Optional[str] = None,
        params: Optional[dict] = None,
        icon: Optional[str] = None,
    ):
        super().__init__(id)
        self.interactive()
        self.set_prop("label", {"literalString": label})
        if icon:
            self.set_prop("icon", {"iconName": icon})
        if action:
            self.set_action(action, params)
