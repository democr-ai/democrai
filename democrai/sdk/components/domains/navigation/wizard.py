from __future__ import annotations

from typing import Any, Dict, List, Optional

from democrai.sdk.components.base import Component


class Wizard(Component):
    """Multi-step workflow component with step state and navigation controls."""
    type = "Wizard"

    def __init__(
        self,
        id: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        *,
        active_step_id: str = "",
        validated_steps: Optional[List[str]] = None,
        action: Any = "",
        params: Optional[dict[str, Any]] = None,
        allow_step_click: bool = True,
        show_controls: bool = True,
        prev_label: str = "Previous",
        next_label: str = "Next",
    ):
        super().__init__(id)
        self.set_prop("steps", steps if steps is not None else [])
        self.set_prop("active_step_id", active_step_id)
        self.set_prop("validated_steps", validated_steps if validated_steps is not None else [])
        self.set_prop("action", action)
        self.set_prop("params", params if params is not None else {})
        self.set_prop("allow_step_click", allow_step_click)
        self.set_prop("show_controls", show_controls)
        self.set_prop("prev_label", prev_label)
        self.set_prop("next_label", next_label)
