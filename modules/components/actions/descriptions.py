from __future__ import annotations

from democrai.sdk.auth import permission_required
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


_DESCRIPTIONS_MODEL = [
    {"field": "full_name", "label": "Full name", "type": "str"},
    {"field": "role", "label": "Role", "type": "str", "transform": "title"},
    {"field": "active", "label": "Active", "type": "bool"},
    {"field": "login_count", "label": "Logins", "type": "int"},
    {"field": "credit", "label": "Credit", "type": "float", "format": ".2f"},
    {"field": "signup_at", "label": "Signup date", "type": "datetime", "format": "%d/%m/%Y %H:%M"},
    {"field": "tags", "label": "Tags", "transform": "join_list|, |upper", "placeholder": "No tags"},
    {"field": "notes", "label": "Notes", "transform": "truncate|36", "placeholder": "No notes"},
]

_DESCRIPTIONS_DATA = {
    "full_name": "Lina Bianchi",
    "role": "platform owner",
    "active": True,
    "login_count": 84,
    "credit": 2450.75,
    "signup_at": "2026-03-21T09:30:00",
    "tags": ["owner", "billing", "security"],
    "notes": "Primary account owner with elevated operational permissions.",
}


@action("descriptions_update")
@permission_required(["components.documentation.view"])
async def descriptions_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_complex/descriptions/model": _DESCRIPTIONS_MODEL,
                "/components_complex/descriptions/data": _DESCRIPTIONS_DATA,
                "/components_complex/descriptions/key_header": "Field",
                "/components_complex/descriptions/value_header": "Runtime value",
                "/components_complex/descriptions/borders": False,
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_complex/descriptions/model": _DESCRIPTIONS_MODEL,
                "/components_complex/descriptions/data": _DESCRIPTIONS_DATA,
                "/components_complex/descriptions/key_header": "Field",
                "/components_complex/descriptions/value_header": "Global value",
                "/components_complex/descriptions/borders": False,
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {
                "components_complex": {
                    "descriptions_model": {
                        "model": _DESCRIPTIONS_MODEL,
                        "data": _DESCRIPTIONS_DATA,
                        "key_header": "Field",
                        "value_header": "Data value",
                        "borders": False,
                    }
                }
            },
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_complex_descriptions_direct",
                "model",
                _DESCRIPTIONS_MODEL,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_descriptions_direct",
                "data",
                _DESCRIPTIONS_DATA,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_descriptions_direct",
                "key_header",
                "Field",
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_descriptions_direct",
                "value_header",
                "Direct value",
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_descriptions_direct",
                "borders",
                False,
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()
