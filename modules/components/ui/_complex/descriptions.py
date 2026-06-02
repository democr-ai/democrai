from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_MODEL = [
    {"field": "full_name", "label": "Full name", "type": "str"},
    {"field": "role", "label": "Role", "type": "str", "transform": "title"},
    {"field": "active", "label": "Active", "type": "bool"},
    {"field": "login_count", "label": "Logins", "type": "int"},
    {"field": "credit", "label": "Credit", "type": "float", "format": ".2f"},
    {"field": "signup_at", "label": "Signup date", "type": "datetime", "format": "%d/%m/%Y %H:%M"},
    {"field": "tags", "label": "Tags", "transform": "join_list|, |upper", "placeholder": "No tags"},
    {"field": "notes", "label": "Notes", "transform": "truncate|36", "placeholder": "No notes"},
    {"field": "missing", "label": "Missing value", "placeholder": "Not provided"},
]

_DATA = {
    "full_name": "Lina Bianchi",
    "role": "platform admin",
    "active": True,
    "login_count": 42,
    "credit": 1234.5,
    "signup_at": "2026-03-21T09:30:00",
    "tags": ["owner", "billing", "security"],
    "notes": "Primary account owner with elevated operational permissions.",
}

_FALLBACK_DATA = {
    "order_id": "ORD-2026-0042",
    "status": "shipped",
    "total": 289.9,
}


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/descriptions"), components=True)

    builder.set_store("/components_complex/descriptions/model", _MODEL, scope="page")
    builder.set_store("/components_complex/descriptions/data", _DATA, scope="page")
    builder.set_store("/components_complex/descriptions/key_header", "Property", scope="page")
    builder.set_store("/components_complex/descriptions/value_header", "Value", scope="page")
    builder.set_store("/components_complex/descriptions/borders", True, scope="page")
    builder.set_store("/components_complex/descriptions/model", _MODEL, scope="global")
    builder.set_store("/components_complex/descriptions/data", _DATA, scope="global")
    builder.set_store("/components_complex/descriptions/key_header", "Property", scope="global")
    builder.set_store("/components_complex/descriptions/value_header", "Value", scope="global")
    builder.set_store("/components_complex/descriptions/borders", True, scope="global")
    builder.set_data(
        "/components_complex/descriptions_model",
        {
            "model": _MODEL,
            "data": _DATA,
            "key_header": "Property",
            "value_header": "Value",
            "borders": True,
        },
    )
    builder.set_data(
        "/components_complex/descriptions_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "model: [...]\ndata: {...}",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "{type: store, scope: page, path: /components_complex/descriptions/data}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "{type: store, scope: global, path: /components_complex/descriptions/data}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_complex/descriptions_model/data",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_complex/descriptions_properties",
        [
            {
                "property": "model",
                "type": "list[dict]",
                "usage": sdk.i18n.t("components.complex.descriptions.property.model"),
            },
            {
                "property": "data",
                "type": "dict",
                "usage": sdk.i18n.t("components.complex.descriptions.property.data"),
            },
            {
                "property": "key_header / value_header",
                "type": "str",
                "usage": sdk.i18n.t("components.complex.descriptions.property.headers"),
            },
            {
                "property": "borders",
                "type": "bool",
                "usage": sdk.i18n.t("components.complex.descriptions.property.borders"),
            },
        ],
    )
    builder.set_data("/components_complex/descriptions_fallback", _FALLBACK_DATA)

    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_descriptions_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
