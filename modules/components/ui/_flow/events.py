from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    builder.merge(sdk.ui.load("ui/yaml/flow_events"), components=True)
    builder.set_data(
        "/components_flow/events/concepts",
        [
            {
                "concept": "event_slot",
                "api": "@sdk.event_slot(...)",
                "usage": sdk.i18n.t("components.flow.events.concept.slot"),
            },
            {
                "concept": "event_listener",
                "api": "@sdk.event_listener(...)",
                "usage": sdk.i18n.t("components.flow.events.concept.listener"),
            },
            {
                "concept": "emit",
                "api": "await sdk.events.emit(...)",
                "usage": sdk.i18n.t("components.flow.events.concept.emit"),
            },
        ],
    )
    builder.set_data(
        "/components_flow/events/api",
        [
            {
                "operation": "sdk.events.qualify_event_name(name)",
                "usage": sdk.i18n.t("components.flow.events.api.qualify"),
            },
            {
                "operation": "sdk.events.get_event_slots(module_name=None)",
                "usage": sdk.i18n.t("components.flow.events.api.slots"),
            },
            {
                "operation": "sdk.events.emit(name, payload=..., session=...)",
                "usage": sdk.i18n.t("components.flow.events.api.emit"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_flow_events_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
