from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


_MIME_OPTIONS = [
    {"label": "PNG", "value": "image/png"},
    {"label": "JPEG", "value": "image/jpeg"},
    {"label": "WebP", "value": "image/webp"},
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/form_tags"), components=True)

    builder.set_store("/components_forms/tags/value", ["image/png"], scope="page")
    builder.set_store("/components_forms/tags/value", ["image/png"], scope="global")
    builder.set_data("/components_forms/tags_model", {"value": ["image/png"]})
    builder.set_data("/components_forms/mime_options", _MIME_OPTIONS)
    builder.set_data(
        "/components_forms/tags_bindings",
        [
            {"binding": "Literal", "yaml": "value: [image/png]", "source": "YAML or Python constructor"},
            {"binding": "Page store", "yaml": "{type: store, scope: page, path: /components_forms/tags/value}", "source": 'builder.set_store(..., scope="page")'},
            {"binding": "Global store", "yaml": "{type: store, scope: global, path: /components_forms/tags/value}", "source": 'builder.set_store(..., scope="global")'},
            {"binding": "Data model", "yaml": "@data/components_forms/tags_model/value", "source": "builder.set_data(...)"},
        ],
    )
    builder.set_data(
        "/components_forms/tags_properties",
        [
            {"property": "label", "type": "str", "usage": sdk.i18n.t("components.forms.tags.property.label")},
            {"property": "value", "type": "list | binding", "usage": sdk.i18n.t("components.forms.tags.property.value")},
            {"property": "placeholder, add_label", "type": "str", "usage": sdk.i18n.t("components.forms.tags.property.labels")},
            {"property": "item_schema", "type": "dict", "usage": sdk.i18n.t("components.forms.tags.property.schema")},
            {"property": "action, params", "type": "action", "usage": sdk.i18n.t("components.forms.tags.property.actions")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_forms_tags_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
