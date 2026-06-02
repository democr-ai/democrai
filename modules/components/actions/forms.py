from __future__ import annotations

from democrai.sdk.auth import permission_required
import json

from democrai.sdk.decorators import action


def _state_update(sdk, scope: str, values: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages([{"stateUpdate": {"scope": scope, "values": values}}])
    )


def _data_update(sdk, surface_id: str, data: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [sdk.ui.Builder.build_data_model_update_payload(surface_id=surface_id, data=data)]
        )
    )


_VALUES = {
    "textfield": {
        "property": "value",
        "value": "Updated short text",
        "path": "/components_forms/textfield/value",
        "model": "textfield_model",
        "component": "components_forms_textfield_direct",
    },
    "textarea": {
        "property": "value",
        "value": "Updated notes from the runtime action.",
        "path": "/components_forms/textarea/value",
        "model": "textarea_model",
        "component": "components_forms_textarea_direct",
    },
    "checkbox": {
        "property": "checked",
        "value": True,
        "path": "/components_forms/checkbox/checked",
        "model": "checkbox_model",
        "component": "components_forms_checkbox_direct",
    },
    "toggle": {
        "property": "checked",
        "value": True,
        "path": "/components_forms/toggle/checked",
        "model": "toggle_model",
        "component": "components_forms_toggle_direct",
    },
    "datepicker": {
        "property": "value",
        "value": "2026-05-09",
        "path": "/components_forms/datepicker/value",
        "model": "datepicker_model",
        "component": "components_forms_datepicker_direct",
    },
    "select": {
        "property": "value",
        "value": "published",
        "path": "/components_forms/select/value",
        "model": "select_model",
        "component": "components_forms_select_direct",
    },
    "radio": {
        "property": "value",
        "value": "large",
        "path": "/components_forms/radio/value",
        "model": "radio_model",
        "component": "components_forms_radio_direct",
    },
    "tags": {
        "property": "value",
        "value": ["image/png", "image/webp"],
        "path": "/components_forms/tags/value",
        "model": "tags_model",
        "component": "components_forms_tags_direct",
    },
    "editable_list": {
        "property": "value",
        "value": ["chat", "reasoning", "tool_calling"],
        "path": "/components_forms/editable_list/value",
        "model": "editable_list_model",
        "component": "components_forms_editable_list_direct",
    },
}


_MODEL_VALUES = {
    "page_store": {
        "title": "Updated from page store",
        "owner": "Katherine",
        "priority": "urgent",
        "notify": True,
    },
    "global_store": {
        "title": "Updated from global store",
        "owner": "Alan",
        "priority": "medium",
        "notify": False,
    },
    "data": {
        "title": "Updated from data model",
        "owner": "Hedy",
        "priority": "high",
        "notify": True,
    },
}


@action("form_model_values_update")
@permission_required(["components.documentation.view"])
async def form_model_values_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
    values = _MODEL_VALUES.get(mode)
    if values is None:
        return sdk.effects.respond()

    if mode == "page_store":
        return _state_update(sdk, "page", {"/components_forms/model/page_values": values})
    if mode == "global_store":
        return _state_update(sdk, "global", {"/components_forms/model/global_values": values})
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_forms": {"model_data": {"values": values}}},
        )

    return sdk.effects.respond()


@action("form_model_submit")
@permission_required(["components.documentation.view"])
async def form_model_submit(ctx: dict, session: dict, sdk) -> dict:
    form_id = str(ctx.get("form_id") or "").strip()
    values = ctx.get(form_id, {}) if form_id else {}
    rendered_value = json.dumps(values, ensure_ascii=False, indent=2)
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": f"{form_id or 'form'} submit",
                "text": rendered_value,
                "variant": "info",
                "duration": 3600,
            },
        )
    )


@action("form_input_update")
@permission_required(["components.documentation.view"])
async def form_input_update(ctx: dict, session: dict, sdk) -> dict:
    component = str(ctx.get("component") or "")
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
    spec = _VALUES.get(component)
    if spec is None:
        return sdk.effects.respond()

    if mode == "page_store":
        return _state_update(sdk, "page", {spec["path"]: spec["value"]})
    if mode == "global_store":
        return _state_update(sdk, "global", {spec["path"]: spec["value"]})
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_forms": {spec["model"]: {spec["property"]: spec["value"]}}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                spec["component"],
                spec["property"],
                spec["value"],
                surface_id=surface_id,
            )
        )

    return sdk.effects.respond()
