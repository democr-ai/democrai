from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    builder.merge(sdk.ui.load("ui/yaml/flow_stream_binding"), components=True)
    builder.set_store("/components_flow/stream_binding/latest/cpu", 0, scope="page")
    builder.set_store("/components_flow/stream_binding/latest/ram", 0, scope="page")
    builder.set_store("/components_flow/stream_binding/latest/vram", 0, scope="page")
    builder.set_store(
        "/components_flow/stream_binding/latest/label",
        sdk.i18n.t("components.flow.stream_binding.waiting"),
        scope="page",
    )
    builder.set_store("/components_flow/stream_binding/cpu/data", [], scope="page")
    builder.set_store("/components_flow/stream_binding/ram/data", [], scope="page")
    builder.set_store("/components_flow/stream_binding/vram/data", [], scope="page")
    builder.set_data(
        "/components_flow/stream_binding/bindings",
        [
            {
                "binding": "Latest sample",
                "stream": "system.runtime.metrics.events",
                "mode": "set",
                "target": "/components_flow/stream_binding/latest",
            },
            {
                "binding": "CPU window",
                "stream": "system.runtime.metrics.events",
                "mode": "append_window",
                "target": "/components_flow/stream_binding/cpu",
            },
            {
                "binding": "RAM window",
                "stream": "system.runtime.metrics.events",
                "mode": "append_window",
                "target": "/components_flow/stream_binding/ram",
            },
            {
                "binding": "VRAM window",
                "stream": "system.runtime.metrics.events",
                "mode": "append_window",
                "target": "/components_flow/stream_binding/vram",
            },
        ],
    )
    builder.set_data(
        "/components_flow/stream_binding/properties",
        [
            {
                "property": "stream",
                "type": "str",
                "usage": sdk.i18n.t("components.flow.stream_binding.property.stream"),
            },
            {
                "property": "event",
                "type": "str",
                "usage": sdk.i18n.t("components.flow.stream_binding.property.event"),
            },
            {
                "property": "target.store",
                "type": "page | global",
                "usage": sdk.i18n.t("components.flow.stream_binding.property.store"),
            },
            {
                "property": "target.mode",
                "type": "set | append_window",
                "usage": sdk.i18n.t("components.flow.stream_binding.property.mode"),
            },
            {
                "property": "target.mappings",
                "type": "dict[str, str]",
                "usage": sdk.i18n.t("components.flow.stream_binding.property.mappings"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_flow_stream_binding_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
