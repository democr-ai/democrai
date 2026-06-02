from __future__ import annotations

from typing import Any

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.decorators import public, template


def _mb_label(value: Any) -> str:
    try:
        mb = int(value or 0)
    except Exception:
        mb = 0
    if mb <= 0:
        return "0 MB"
    gb = mb / 1024
    if gb >= 1:
        return f"{gb:.1f} GB"
    return f"{mb} MB"


def _warning_text(resource_warning: dict[str, Any]) -> str:
    warnings = resource_warning.get("warnings")
    if not isinstance(warnings, list) or not warnings:
        return ""
    lines: list[str] = []
    for item in warnings:
        if not isinstance(item, dict):
            continue
        resource = str(item.get("resource") or "").strip().upper()
        required = _mb_label(item.get("required_mb"))
        available = _mb_label(item.get("available_mb"))
        lines.append(f"{resource}: required {required}, available {available}")
    return "\n".join(lines)


@template("empty")
@public
async def render(params: dict[str, Any], session: dict) -> sdk.ui.Builder:
    builder = sdk.ui.load("utils/ui/yaml/engine/model_catalog_resource_warning")
    catalog_id = str(params.get("catalog_id") or "").strip()
    engine_id = int(params["engine_id"])
    provider = str(params.get("provider") or "").strip()
    task_mount_id = str(params.get("task_mount_id") or "").strip()
    action_name = str(
        params.get("action_name") or "system.download_engine_model_catalog"
    ).strip()
    label = str(params.get("label") or "").strip() or "model"
    resource_warning = (
        dict(params.get("resource_warning"))
        if isinstance(params.get("resource_warning"), dict)
        else {}
    )
    items = list(params.get("items") or []) if isinstance(params.get("items"), list) else []
    builder.set_data(
        "/engine/model/catalog/resource_warning",
        {
            "title": f"Resource warning for {label}",
            "text": _warning_text(resource_warning),
        },
    )
    confirm = builder.get_component("engine_model_catalog_resource_warning_confirm")
    if confirm is not None:
        confirm.set_property("action", {"name": action_name, "context": {}})
        confirm.set_property(
            "params",
            {
                "catalog_id": catalog_id,
                "engine_id": engine_id,
                "provider": provider,
                "task_mount_id": task_mount_id,
                "confirmed_resource_warning": True,
                "items": items,
            },
        )
    return builder
