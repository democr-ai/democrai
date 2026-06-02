from typing import Dict, Any, Optional
from democrai.sdk.components.base import Component

class Button(Component):
    """Interactive button component for explicit user-triggered actions."""
    type = "Button"

    def __init__(
        self,
        id: str,
        label: str,
        action: Optional[str] = None,
        params: Optional[dict] = None,
        icon: Optional[str] = None,
        variant: str = "default",  # default, secondary, destructive, ghost, link (+ legacy aliases)
        mode: str = "solid",  # legacy: solid, ghost, link
        appearance: Optional[str] = None,  # shadcn-like: default, secondary, outline, ghost, link
        btnsize: str = "normal",  # sm/default/lg (+ legacy small/normal/large)
        shape: str = "default",  # default, round/icon
    ):
        super().__init__(id)
        self.interactive()
        self.set_prop("label", {"literalString": label})
        self.set_prop("variant", variant)
        self.set_prop("mode", mode)
        if appearance:
            self.set_prop("appearance", appearance)
        self.set_prop("btnsize", btnsize)
        self.set_prop("shape", shape)
        if icon:
            self.set_prop("icon", {"iconName": icon})
        if action:
            self.set_action(action, params)
            self._auto_collect_input_for_show_value(action, params)

    @staticmethod
    def _is_show_value_action(name: str) -> bool:
        """Return whether the action name matches the preview show-value helper."""
        action_name = str(name or "").strip()
        if not action_name:
            return False
        # Supports both plain and namespaced forms:
        # - form_preview_show_value
        # - components.form_preview_show_value
        return action_name.endswith("form_preview_show_value")

    def _auto_collect_input_for_show_value(self, name: str, context: Optional[dict]) -> None:
        """Auto-populate collected input ids for preview show-value actions."""
        if not self._is_show_value_action(name):
            return
        if not isinstance(context, dict):
            return
        input_id = str(context.get("input_id") or "").strip()
        if not input_id:
            return
        existing = self.props.get("collect_input_ids")
        if isinstance(existing, list) and input_id in existing:
            return
        self.set_prop("collect_input_ids", [input_id])

    def set_action(self, name: str, context: Optional[dict] = None):
        """Attach the action and auto-configure preview-specific input collection."""
        payload = context if context is not None else {}
        super().set_action(name, payload)
        self._auto_collect_input_for_show_value(name, payload)
        return self
