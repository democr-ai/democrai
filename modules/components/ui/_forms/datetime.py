from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/form_datepicker"), components=True)

    builder.set_store("/components_forms/datepicker/value", "2026-04-24", scope="page")
    builder.set_store("/components_forms/datepicker/value", "2026-04-24", scope="global")
    builder.set_data("/components_forms/datepicker_model", {"value": "2026-04-24"})
    builder.set_data(
        "/components_forms/datepicker_bindings",
        [
            {"binding": "Literal", "yaml": 'value: "2026-04-24"', "source": "YAML or Python constructor"},
            {"binding": "Page store", "yaml": "{type: store, scope: page, path: /components_forms/datepicker/value}", "source": 'builder.set_store(..., scope="page")'},
            {"binding": "Global store", "yaml": "{type: store, scope: global, path: /components_forms/datepicker/value}", "source": 'builder.set_store(..., scope="global")'},
            {"binding": "Data model", "yaml": "@data/components_forms/datepicker_model/value", "source": "builder.set_data(...)"},
        ],
    )
    builder.set_data(
        "/components_forms/datepicker_properties",
        [
            {"property": "label", "type": "str", "usage": sdk.i18n.t("components.forms.datepicker.property.label")},
            {"property": "value", "type": "str | binding", "usage": sdk.i18n.t("components.forms.datepicker.property.value")},
            {"property": "min_date, max_date", "type": "str", "usage": sdk.i18n.t("components.forms.datepicker.property.range")},
            {"property": "format", "type": "str", "usage": sdk.i18n.t("components.forms.datepicker.property.format")},
            {"property": "max_width", "type": "int | None", "usage": sdk.i18n.t("components.forms.datepicker.property.max_width")},
            {"property": "action, params", "type": "action", "usage": sdk.i18n.t("components.forms.datepicker.property.actions")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_forms_datepicker_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
