from __future__ import annotations

from typing import Any


class AgentUIBridge:
    """Translate high-level agent UI commands to validated property updates."""

    _ACTION_BY_OP = {
        "set_property": "set",
        "append_property": "append",
        "remove_property": "remove",
        "replace_property": "replace",
    }

    def __init__(self, window: Any, property_controller: Any) -> None:
        self.window = window
        self.property_controller = property_controller

    def apply_commands(self, commands: list[dict[str, Any]]) -> dict[str, Any]:
        report = {"applied": [], "rejected": []}
        for command in commands:
            update = self._to_property_update(command)
            if update is None:
                report["rejected"].append(
                    {
                        "command": command,
                        "reason": "unsupported_or_invalid",
                    }
                )
                continue
            if not self.property_controller.is_update_allowed(update):
                report["rejected"].append(
                    {
                        "command": command,
                        "reason": "capability_denied",
                    }
                )
                continue
            self.property_controller.enqueue(update)
            report["applied"].append(command)
        return report

    def _to_property_update(self, command: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(command, dict):
            return None

        op = str(command.get("op") or "set_property").strip()
        component_id = command.get("componentId")
        property_name = command.get("propertyName")
        if op not in self._ACTION_BY_OP:
            return None
        if not component_id or not property_name:
            return None

        action = self._ACTION_BY_OP[op]
        if op == "set_property":
            action = str(command.get("action") or "set").strip() or "set"

        update = {
            "surfaceId": str(command.get("surfaceId") or "main"),
            "componentId": str(component_id),
            "propertyName": str(property_name),
            "action": action,
            "value": command.get("value"),
        }
        return update
