from __future__ import annotations

import json

from democrai.sdk.client import active_sdk as sdk


def _entity_id(params: dict) -> str:
    route_params = params.get("route_params") if isinstance(params.get("route_params"), dict) else {}
    return str(route_params.get("id") or "").strip()


async def render(params: dict, session: dict):
    entity_id = _entity_id(params)
    is_create = entity_id in {"", "new"}
    row = None if is_create else sdk.models.mcp_server_registry.view(int(entity_id))
    builder = sdk.ui.load("utils/ui/yaml/mcp/form")
    title = builder.get_component("system_mcp_form_title")
    if title is not None:
        title.set_property(
            "text",
            sdk.i18n.t("system.mcp.form.create_title")
            if is_create
            else sdk.i18n.t(
                "system.mcp.form.update_title",
                context={"name": str(row.get("name") or "")},
            ),
        )
    form = builder.get_component("system_mcp_form")
    if form is not None:
        model = (
            sdk.models.mcp_server_registry.form_model_create()
            if is_create
            else sdk.models.mcp_server_registry.form_model_update(int(entity_id))
        )
        form.set_property("model", model)
        form.set_property("params", {"id": "new" if is_create else int(entity_id)})
        if row is not None:
            form.set_property(
                "values",
                {
                    "name": row.get("name"),
                    "transport": row.get("transport"),
                    "endpoint_url": row.get("endpoint_url"),
                    "config": json.dumps(row.get("config") or {}, indent=2),
                    "enabled": bool(row.get("enabled")),
                    "timeout_ms": str(row.get("timeout_ms") or 15000),
                },
            )
    return builder
