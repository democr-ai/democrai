from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.ui.engine.list import (
    add_provider_cards,
    cards_from_rows,
    ensure_non_configurable_engines,
    provider_catalog,
    section_title,
)


async def render(params: dict, session: dict):

    route_params = dict(params.get("route_params") or {})
    domain = str(route_params.get("domain") or "").strip()

    builder = sdk.ui.Builder()
    root = sdk.ui.Column(
        "engine_provider_domain_page",
        ["engine_provider_domain_info", "engine_provider_domain_cards"],
    )
    root.set_property("spacing", 14)
    builder.add(root)
    container = sdk.ui.FlexContainer("engine_provider_domain_cards", [])
    builder.add(container)

    catalog = provider_catalog()
    if domain not in catalog:
        return builder

    description_key = f"system.engine.list.section.{domain}.description"
    description = sdk.i18n.t(description_key)
    if description == description_key:
        description = ""
    alert = sdk.ui.Alert(
        "engine_provider_domain_info",
        title=section_title(sdk.i18n.t, domain),
        description=description,
        variant="info",
    )
    alert.set_property("style", "margin-top: 12px; margin-bottom: 4px;")
    builder.add(alert)

    section_catalog = {domain: catalog[domain]}
    engine_rows = ensure_non_configurable_engines()
    sections = cards_from_rows(catalog=section_catalog, engine_rows=engine_rows)
    add_provider_cards(
        builder,
        sections=sections,
        engine_rows=engine_rows,
        container_id="engine_provider_domain_cards",
        t=sdk.i18n.t,
    )

    return builder
