from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


_STATIC_VALUES = {
    "title": "Static onboarding",
    "owner": "Ada",
    "priority": "medium",
    "notify": True,
}

_PAGE_VALUES = {
    "title": "Page-store onboarding",
    "owner": "Grace",
    "priority": "high",
    "notify": True,
}

_GLOBAL_VALUES = {
    "title": "Global-store onboarding",
    "owner": "Linus",
    "priority": "low",
    "notify": False,
}

_DATA_VALUES = {
    "title": "Data-model onboarding",
    "owner": "Margaret",
    "priority": "urgent",
    "notify": True,
}


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/form_model"), components=True)

    builder.set_store("/components_forms/model/page_values", _PAGE_VALUES, scope="page")
    builder.set_store("/components_forms/model/global_values", _GLOBAL_VALUES, scope="global")
    builder.set_data("/components_forms/model_data", {"values": _DATA_VALUES})
    builder.set_data(
        "/components_forms/model_bindings",
        [
            {
                "binding": "Static values",
                "yaml": "values: {title: Static onboarding, priority: medium}",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "{type: store, scope: page, path: /components_forms/model/page_values}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "{type: store, scope: global, path: /components_forms/model/global_values}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_forms/model_data/values",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_forms/model_properties",
        [
            {
                "property": "model",
                "type": "list[dict]",
                "usage": sdk.i18n.t("components.forms.model.property.model"),
            },
            {
                "property": "values",
                "type": "dict | binding",
                "usage": sdk.i18n.t("components.forms.model.property.values"),
            },
            {
                "property": "submit_label",
                "type": "str",
                "usage": sdk.i18n.t("components.forms.model.property.submit_label"),
            },
            {
                "property": "action, params",
                "type": "action",
                "usage": sdk.i18n.t("components.forms.model.property.action"),
            },
            {
                "property": "track_loading",
                "type": "str | list[str]",
                "usage": sdk.i18n.t("components.forms.model.property.loading"),
            },
            {
                "property": "errors",
                "type": "dict[str, str]",
                "usage": sdk.i18n.t("components.forms.model.property.errors"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_forms_model_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
