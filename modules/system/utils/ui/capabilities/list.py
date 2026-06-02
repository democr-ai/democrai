from __future__ import annotations

import re
from typing import Any

from democrai.sdk.ui import merge_builders


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _slug_capability(capability: str) -> str:
    return (
        re.sub(r"[^a-z0-9_]+", "_", _safe_text(capability).lower()).strip("_") or "cap"
    )


def pane_id_for_capability(capability: str) -> str:
    return f"system_capability_{_slug_capability(capability)}_pane"


def priority_select_id(capability: str, priority: int) -> str:
    return (
        f"system_capability_{_slug_capability(capability)}_priority_{priority}_select"
    )


def priority_save_id(capability: str) -> str:
    return f"system_capability_{_slug_capability(capability)}_priority_save"


def capability_label(module_sdk, capability: str) -> str:
    normalized = _safe_text(capability).lower()
    key = f"system.capabilities.capability.{normalized}"
    translated = module_sdk.i18n.t(key)
    if translated == key:
        return normalized
    return translated


def capability_icon(capability: str) -> str:
    key = _safe_text(capability).lower()
    mapping = {
        "chat": "ric.message-3-line",
        "tool_calling": "ric.tools-line",
        "reasoning": "ric.brain-line",
        "image_to_text": "ric.image-line",
        "detection": "ric.scan-line",
        "video": "ric.video-line",
        "code": "ric.code-s-slash-line",
        "embedding": "ric.node-tree",
        "audio": "ric.volume-up-line",
        "tts": "ric.voiceprint-line",
        "stt": "ric.mic-line",
    }
    return mapping.get(key, "ric.function-line")


def build_capability_tab(
    builder,
    module_sdk,
    capability: str,
    form_data: dict[str, Any],
) -> tuple[str, dict[str, str]]:
    pane_id = pane_id_for_capability(capability)

    tab_builder = module_sdk.ui.load("utils/ui/yaml/capabilities/model_list_tab")
    pane_component = tab_builder.get_component("capability_priority_pane")
    if pane_component is not None:
        pane_component.id = pane_id

    options = list(form_data.get("options") or [])
    values = dict(form_data.get("values") or {})
    for priority in range(1, 4):
        name = f"priority_{priority}"
        select_component = tab_builder.get_component(
            f"capability_priority_{priority}_select"
        )
        if select_component is None:
            continue
        select_component.id = priority_select_id(capability, priority)
        select_component.set_property("options", options)
        select_component.set_property("value", values.get(name, ""))

    save_component = tab_builder.get_component("capability_priority_save")
    if save_component is not None:
        save_component.id = priority_save_id(capability)
        input_ids = [
            priority_select_id(capability, priority) for priority in range(1, 4)
        ]
        save_component.set_property("collect_input_ids", input_ids)
        save_component.set_property(
            "action",
            {
                "name": "system.save_capability_priorities",
                "context": {"capability": capability},
            },
        )
        save_component.set_property(
            "track_loading", "system.save_capability_priorities"
        )

    empty_component = tab_builder.get_component("capability_priority_empty")
    if empty_component is not None:
        empty_component.set_property("visible", not bool(form_data.get("has_models")))
    editor_component = tab_builder.get_component("capability_priority_editor")
    if editor_component is not None:
        editor_component.set_property("visible", bool(form_data.get("has_models")))
    if save_component is not None:
        save_component.set_property("visible", bool(form_data.get("has_models")))

    merge_builders(builder, tab_builder)

    return pane_id, {
        "id": pane_id,
        "label": capability_label(module_sdk, capability),
        "icon": capability_icon(capability),
    }
