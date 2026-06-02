from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.engines import list_provider_definitions

from modules.system.ui.layout import shared_layout
from modules.system.utils.ui.engine.provider_page import (
    capability_label,
    provider_engine_cards,
    provider_engine_rows,
)
from democrai.sdk.ui import merge_builders


async def render(params: dict, session: dict):
    route_params = dict(params.get("route_params") or {})
    current_provider = str(route_params.get("provider") or "").strip().lower()

    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    merge_builders(builder, sdk.ui.load("utils/ui/yaml/engine/provider_configurable"))

    defs = list_provider_definitions()
    provider = None
    for p in defs:
        if p.get("id") == current_provider:
            provider = p
            break

    if not provider:
        return None

    listing = sdk.models.engine_registry.list(
        filters={"provider": current_provider},
    )
    provider_engines = provider_engine_rows(listing, sdk.i18n.t)

    provider_payload = dict(provider)
    provider_payload["config_path"] = (
        f"/system/engine/provider/config/{current_provider}"
    )

    builder.set_store("/current_provider", provider_payload)
    builder.set_store("/provider_engines", provider_engines)
    builder.set_store("/provider_engines_empty", len(provider_engines) == 0)

    icon = builder.get_component("engine_provider_info_icon")
    if icon is not None:
        icon.set_property("url", provider.get("icon_url", None))

    capability_ids: list[str] = []
    for index, capability in enumerate(provider.get("capabilities") or []):
        capability_text = capability_label(sdk.i18n.t, str(capability))
        if not capability_text:
            continue
        badge_id = f"engine_provider_capability_{index}"
        builder.add(sdk.ui.Badge(badge_id, capability_text, variant="info"))
        capability_ids.append(badge_id)

    capabilities_row = builder.get_component("engine_provider_info_capabilities")
    if capabilities_row is not None:
        capabilities_row.set_children(capability_ids)

    instance_cards = provider_engine_cards(provider_engines, sdk.i18n.t)
    instances_flow = sdk.ui.Flow("engine_provider_instances_flow", spacing=16)
    instances_flow.set_children(instance_cards)
    builder.add(instances_flow)

    instances_container = builder.get_component("engine_provider_instances_cards")
    if instances_container is not None:
        instances_container.set_children([instances_flow])

    task_mount = builder.get_component("engine_provider_task_mount_col")
    if task_mount is not None:
        task_mount.allow("children.append")

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(["engine_provider_config_page"])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
