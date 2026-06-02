from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


@action("typography_update")
@permission_required(["components.documentation.view"])
async def typography_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "").strip()
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "store":
        return sdk.effects.respond(
            sdk.effects.ui_messages(
                [
                    {
                        "stateUpdate": {
                            "scope": "page",
                            "values": {
                                "/components_typography/store_title": sdk.i18n.t(
                                    "components.typography.usage.store_title"
                                ),
                                "/components_typography/store_text": sdk.i18n.t(
                                    "components.typography.usage.store_text"
                                ),
                            },
                        }
                    }
                ]
            )
        )

    if mode == "data":
        return sdk.effects.respond(
            sdk.effects.ui_messages(
                [
                    sdk.ui.Builder.build_data_model_update_payload(
                        surface_id=surface_id,
                        data={
                            "components_typography": {
                                "data_title": sdk.i18n.t(
                                    "components.typography.usage.data_title"
                                ),
                                "data_text": sdk.i18n.t(
                                    "components.typography.usage.data_text"
                                ),
                                "data_markdown": sdk.i18n.t(
                                    "components.typography.usage.data_markdown"
                                ),
                            }
                        },
                    )
                ]
            )
        )

    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_typography_direct_title",
                "text",
                sdk.i18n.t("components.typography.usage.direct_title"),
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_typography_direct_title",
                "level",
                2,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_typography_direct_text",
                "text",
                sdk.i18n.t("components.typography.usage.direct_text"),
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_typography_direct_text",
                "align",
                "center",
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()
