from __future__ import annotations

from copy import deepcopy
from typing import Any

from modules.chat.models import ChatComponent
from modules.chat.utils.actions.a2ui_schema import (
    A2UIValidationError,
    SUPPORTED_COMPONENTS,
    chat_component_id,
    validate_a2ui_component,
)
from modules.chat.utils.actions.messages import next_sequence
from modules.chat.utils.ui.rows import component_model_row


def normalize_component_payload(
    component_type: str,
    props: dict[str, Any],
    children: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    payload = build_a2ui_component(component_type, props, children or [])
    if not str(payload.get("id") or "").strip():
        payload["id"] = chat_component_id()
    return validate_a2ui_component(payload)


def build_a2ui_component(
    component_type: str,
    props: dict[str, Any],
    children: list[dict[str, Any]],
    component_id: str = "",
) -> dict[str, Any]:
    component_name = _component_name(component_type)
    if not component_name:
        raise A2UIValidationError("type", "unsupported component type")
    if not isinstance(props, dict):
        raise A2UIValidationError("props", "props must be an object")
    if not isinstance(children, list):
        raise A2UIValidationError("children", "children must be an array")
    return {
        "id": component_id or chat_component_id(component_name.lower()),
        "component": {component_name: deepcopy(props)},
        "children": {
            "explicitList": [
                build_a2ui_component_from_child(child, index)
                for index, child in enumerate(children)
            ]
        },
    }


def build_a2ui_component_from_child(child: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(child, dict):
        raise A2UIValidationError(f"children.{index}", "child must be an object")
    return build_a2ui_component(
        child.get("type", ""),
        child.get("props", {}),
        child.get("children", []),
        str(child.get("id") or ""),
    )


def _component_name(value: str) -> str:
    requested = str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    for component in SUPPORTED_COMPONENTS:
        if component.lower() == requested:
            return component
    return ""


def create_component_message(
    module_sdk,
    *,
    conversation_id: int,
    message_id: int | None,
    component_type: str,
    props: dict[str, Any],
    children: list[dict[str, Any]] | None = None,
) -> ChatComponent:
    component_kind, payload = normalize_component_payload(component_type, props, children)
    row = module_sdk.database.add(
        ChatComponent(
            conversation_id=int(conversation_id),
            message_id=int(message_id) if message_id else None,
            sequence=next_sequence(module_sdk, int(conversation_id)),
            component_kind=component_kind,
            payload={"kind": component_kind, "components": [payload]},
        )
    )
    return row


def component_message_row(row: ChatComponent) -> dict[str, Any]:
    return component_model_row(row)
