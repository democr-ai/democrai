from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


@permission_required(["components.documentation.view"])
async def render(params: dict, session: dict) -> sdk.ui.Builder:
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/ai_input"), components=True)

    builder.set_store(
        "/components_ai/input/value",
        "Plan a rollout strategy for introducing the new chat input renderer.",
        scope="page",
    )
    builder.set_store("/components_ai/input/model", "gpt-5.4", scope="page")
    builder.set_store(
        "/components_ai/input/model_capabilities",
        ["reasoning", "ingestion"],
        scope="page",
    )
    builder.set_data(
        "/components_ai/input_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "value: \"Type your prompt...\"",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "type: store\nscope: page\npath: /components_ai/input/value",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_ai/input/value",
                "source": "builder.set_data(...)",
            },
            {
                "binding": "Direct update",
                "yaml": "model.set / model_capabilities.set",
                "source": "sdk.effects.ui_property_update(...)",
            },
        ],
    )
    builder.set_data(
        "/components_ai/input_properties",
        [
            {"property": "placeholder", "type": "str", "usage": sdk.i18n.t("components.ai.input.property.placeholder")},
            {"property": "value", "type": "str", "usage": sdk.i18n.t("components.ai.input.property.value")},
            {"property": "send_action / on_submit", "type": "action", "usage": sdk.i18n.t("components.ai.input.property.submit")},
            {"property": "cancel_action / on_stop_enabled", "type": "action", "usage": sdk.i18n.t("components.ai.input.property.stop")},
            {"property": "models / model", "type": "list[dict] / str", "usage": sdk.i18n.t("components.ai.input.property.model")},
            {"property": "tools / skills", "type": "list[str]", "usage": sdk.i18n.t("components.ai.input.property.tools")},
            {"property": "model_capabilities / show_capabilities", "type": "list[str] / bool", "usage": sdk.i18n.t("components.ai.input.property.capabilities")},
            {"property": "voice / enable_attachment / ingest", "type": "bool", "usage": sdk.i18n.t("components.ai.input.property.flags")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_ai_input_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
