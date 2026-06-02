from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/effect_background_task"), components=True)

    builder.set_store(
        "/background_tasks/components_demo_completed",
        {
            "taskId": "components_demo_completed",
            "label": sdk.i18n.t("components.effects.background.seed.completed"),
            "status": "completed",
            "progress": 1,
            "result": {"processed": 8},
        },
        scope="global",
    )
    builder.set_data(
        "/components_effects/background_task_properties",
        [
            {
                "field": "task_id",
                "type": "str",
                "usage": sdk.i18n.t("components.effects.background.property.task_id"),
            },
            {
                "field": "on_completed",
                "type": "action",
                "usage": sdk.i18n.t("components.effects.background.property.completed"),
            },
            {
                "field": "on_error",
                "type": "action",
                "usage": sdk.i18n.t("components.effects.background.property.error"),
            },
            {
                "field": "on_progress",
                "type": "action",
                "usage": sdk.i18n.t("components.effects.background.property.progress"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_effect_background_task_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
