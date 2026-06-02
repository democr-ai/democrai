from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import AICapability
from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.ui.layout import shared_layout
from modules.system.utils.ui.model.runtime import available_model_name


def _csv(values: Any) -> str:
    if not isinstance(values, list):
        values = [values] if values else []
    return ", ".join(str(item or "").strip() for item in values if str(item or "").strip())


def _engine_label(engine_id: Any) -> str:
    if engine_id in (None, ""):
        return "-"
    engine = sdk.models.engine_registry.view(int(engine_id))
    if not isinstance(engine, dict):
        return "-"
    return str(engine.get("name") or engine.get("provider") or "-").strip() or "-"


def _tool_calling_model_options() -> list[dict[str, Any]]:
    listing = sdk.models.model_registry.all(sort={"field": "name", "direction": "asc"})
    options: list[dict[str, Any]] = []
    for row in list(listing.get("rows") or []):
        if not isinstance(row, dict):
            continue
        capabilities = list(row.get("capabilities") or [])
        if AICapability.TOOL_CALLING not in capabilities:
            continue
        model_name = available_model_name(row)
        engine_name = _engine_label(row.get("engine_id"))
        row_id = row.get("id")
        if row_id in (None, ""):
            continue
        options.append(
            {
                "label": f"{model_name or row_id} - {engine_name}",
                "value": int(row_id),
            }
        )
    return options


def _form_model(model_options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected_model = model_options[0]["value"] if model_options else ""
    return [
        {
            "name": "model_row_id",
            "label": sdk.i18n.t("system.mcp.test.field.model"),
            "type": "select",
            "value": selected_model,
            "options": model_options,
            "validations": [{"rule": "required"}],
        },
        {
            "name": "prompt",
            "label": sdk.i18n.t("system.mcp.test.field.prompt"),
            "type": "textarea",
            "value": sdk.i18n.t("system.mcp.test.default_prompt"),
            "validations": [{"rule": "required"}],
        },
    ]


async def render(params: dict, session: dict):
    route_params = params.get("route_params")
    row_id = (
        int(route_params["id"])
        if isinstance(route_params, dict) and "id" in route_params
        else None
    )

    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    page_builder = sdk.ui.load("utils/ui/yaml/mcp/test")
    merge_builders(builder, page_builder)

    row = sdk.models.mcp_server_registry.view(row_id) if row_id is not None else None
    if isinstance(row, dict):
        model_options = _tool_calling_model_options()
        enabled = bool(row.get("enabled"))
        title = str(row.get("name") or "").strip() or sdk.i18n.t("system.mcp.test.title")
        store_payload = {
            "id": int(row["id"]),
            "name": title,
            "transport": str(row.get("transport") or "-"),
            "endpoint_url": str(row.get("endpoint_url") or "-"),
            "enabled": enabled,
            "enabled_text": (
                sdk.i18n.t("system.mcp.test.enabled")
                if enabled
                else sdk.i18n.t("system.mcp.test.disabled")
            ),
            "timeout_ms": str(row.get("timeout_ms") or "-"),
            "models_available": bool(model_options),
            "form": _form_model(model_options),
            "summary": {
                "literalString": "\n".join(
                    [
                        f"Name: {title}",
                        f"Transport: {row.get('transport') or '-'}",
                        f"Endpoint: {row.get('endpoint_url') or '-'}",
                        f"Enabled: {enabled}",
                        f"Tool calling models: {_csv([item['label'] for item in model_options]) or '-'}",
                    ]
                )
            },
            "breadcrumb_segments": [
                {"label": "System", "path": "/system/index"},
                {"label": sdk.i18n.t("system.mcp.title"), "path": "/system/mcp/list"},
                {"label": title, "current": True},
            ],
            "valid": True,
            "last_status": "",
            "last_result": {
                "output": sdk.i18n.t("system.mcp.test.result_empty"),
                "metrics": "",
            },
            "trace_events": [],
        }
    else:
        store_payload = {
            "id": row_id,
            "name": sdk.i18n.t("system.mcp.test.title"),
            "transport": "-",
            "endpoint_url": "-",
            "enabled": False,
            "enabled_text": "-",
            "timeout_ms": "-",
            "models_available": False,
            "form": [],
            "summary": sdk.i18n.t(
                "system.mcp.test.placeholder",
                context={"id": str(row_id or "-")},
            ),
            "breadcrumb_segments": [
                {"label": "System", "path": "/system/index"},
                {"label": sdk.i18n.t("system.mcp.title"), "path": "/system/mcp/list"},
                {"label": sdk.i18n.t("system.mcp.test.title"), "current": True},
            ],
            "valid": False,
            "last_status": "",
            "last_result": {"output": "", "metrics": ""},
            "trace_events": [],
        }

    builder.set_store("/system/mcp/test", store_payload, scope="page")

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(["system_mcp_test_page"])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
