from __future__ import annotations

from typing import Any

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.engines import list_provider_definitions


def _section_key(definition: dict[str, Any]) -> str:
    deployment = str(definition.get("deployment") or "").strip().lower()
    kind = str(definition.get("kind") or "").strip().lower()
    local = str(definition.get("local_section") or "").strip().lower()
    if deployment == "local" and local:
        return local
    return f"{deployment or 'other'}_{kind or 'general'}"


def section_sort_key(section_name: str) -> tuple[int, int, str]:
    normalized = str(section_name or "").strip().lower()
    if "_" in normalized:
        deployment, kind = normalized.split("_", 1)
    else:
        deployment, kind = normalized, "general"

    deployment_rank = {
        "local": 0,
        "hybrid": 1,
        "remote": 2,
        "other": 3,
    }.get(deployment, 9)
    kind_rank = {
        "llm": 0,
        "stt": 1,
        "tts": 2,
        "audio": 3,
        "image_to_text": 4,
        "detection": 5,
        "general": 9,
    }.get(kind, 8)
    return (deployment_rank, kind_rank, normalized)


def _provider_copy(definition: dict[str, Any]) -> dict[str, Any]:
    provider = str(definition.get("id") or "").strip().lower()
    title = str(definition.get("title") or definition.get("label") or provider)
    description = str(
        definition.get("description") or definition.get("description_key") or ""
    )
    capabilities = list(
        definition.get("capabilities") or definition.get("capability_keys") or []
    )

    return {
        "id": provider,
        "provider": provider,
        "name": provider,
        "label": str(definition.get("label") or provider),
        "kind": str(definition.get("kind") or "").strip().lower(),
        "deployment": str(definition.get("deployment") or "").strip().lower(),
        "configurable": bool(definition.get("configurable")),
        "config_schema": [
            dict(item)
            for item in (definition.get("config_schema") or [])
            if isinstance(item, dict)
        ],
        "icon_url": str(definition.get("icon_url") or ""),
        "title": title,
        "description": description,
        "capabilities": [str(key) for key in capabilities if str(key).strip()],
    }


def provider_catalog() -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for definition in list_provider_definitions() or []:
        provider = str(definition.get("id") or "").strip().lower()
        if not provider:
            continue
        section = _section_key(definition)
        result.setdefault(section, []).append(_provider_copy(definition))

    for section in result:
        result[section].sort(key=lambda item: str(item.get("title") or ""))
    return result


def load_all_engines() -> list[dict]:
    page = 0
    page_size = 200
    rows: list[dict] = []
    while True:
        listing = sdk.models.engine_registry.list(
            page=page,
            page_size=page_size,
            filters={},
        )
        batch = listing.get("rows") or []
        for item in batch:
            if isinstance(item, dict):
                rows.append(item)
        total_rows = int(listing.get("total_rows") or 0)
        if len(rows) >= total_rows or not batch:
            break
        page += 1
    return rows


def ensure_non_configurable_engines() -> list[dict]:
    return load_all_engines()


def _has_required_config(
    config_schema: list[dict[str, Any]], config: dict[str, Any] | None
) -> bool:
    values = config if isinstance(config, dict) else {}
    for field in config_schema:
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        required = any(
            isinstance(validation, dict)
            and str(validation.get("rule") or "").strip().lower() == "required"
            for validation in (field.get("validations") or [])
        )
        if not required:
            continue
        value = values.get(name)
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
    return True


def cards_from_rows(
    *,
    catalog: dict[str, list[dict[str, Any]]],
    engine_rows: list[dict],
) -> dict[str, list[dict[str, Any]]]:
    rows_by_provider: dict[str, list[dict]] = {}
    for row in engine_rows:
        if not isinstance(row, dict):
            continue
        provider = str(row.get("provider") or "").strip().lower()
        if not provider:
            continue
        rows_by_provider.setdefault(provider, []).append(row)

    for provider_rows in rows_by_provider.values():
        provider_rows.sort(key=lambda row: int(row.get("id") or 0))

    resolved: dict[str, list[dict[str, Any]]] = {key: [] for key in catalog.keys()}
    for section_name, providers in catalog.items():
        bucket = resolved.setdefault(section_name, [])
        for provider_item in providers:
            provider = str(provider_item.get("provider") or "").strip().lower()
            if not provider:
                continue
            provider_rows = rows_by_provider.get(provider, [])
            card = dict(provider_item)
            card["id"] = provider
            card["engine_id"] = None
            card["engine_name"] = str(provider_item.get("label") or provider)
            card["status"] = provider_status(provider_rows)
            card["engine_count"] = len(provider_rows)
            bucket.append(card)

    return resolved


def provider_list_items(
    *,
    sections: dict[str, list[dict[str, Any]]],
    engine_rows: list[dict],
    t,
) -> list[dict[str, Any]]:
    rows_by_provider: dict[str, list[dict]] = {}
    for row in engine_rows:
        if not isinstance(row, dict):
            continue
        provider = str(row.get("provider") or "").strip().lower()
        if not provider:
            continue
        rows_by_provider.setdefault(provider, []).append(row)

    for provider_rows in rows_by_provider.values():
        provider_rows.sort(key=lambda row: int(row.get("id") or 0))

    items: list[dict[str, Any]] = []
    for section_name, section_items in sorted(
        sections.items(), key=lambda item: section_sort_key(item[0])
    ):
        for item in section_items:
            provider = str(item.get("provider") or "").strip().lower()
            if not provider:
                continue
            provider_rows = rows_by_provider.get(provider, [])
            configurable = bool(item.get("configurable"))
            first = provider_rows[0] if provider_rows else {}
            instance_id = (
                int(first["id"])
                if isinstance(first, dict) and first.get("id")
                else None
            )
            if configurable:
                route = f"/system/engine/provider/{provider}"
            else:
                route = (
                    f"/system/engine/instance/{instance_id}/view" if instance_id else ""
                )

            count_value = max(0, int(item.get("engine_count") or 0))
            capability_text = ", ".join(
                str(value)
                for value in (item.get("capabilities") or [])
                if str(value).strip()
            )
            items.append(
                {
                    "id": provider,
                    "provider": provider,
                    "title": str(item.get("title") or provider),
                    "description": str(item.get("description") or ""),
                    "icon_url": str(
                        item.get("icon_url") or "assets/engines/llamacpp.png"
                    ),
                    "section": section_title(t, section_name),
                    "capabilities": capability_text,
                    "configurable": configurable,
                    "engine_count": count_value,
                    "engine_count_label": t(
                        "system.engine.list.engine_count",
                        context={"count": count_value},
                    ),
                    "status": str(item.get("status") or "uninstalled"),
                    "status_label": provider_status_label(
                        t,
                        str(item.get("status") or "uninstalled"),
                    ),
                    "status_variant": provider_status_variant(
                        str(item.get("status") or "uninstalled")
                    ),
                    "route": route,
                }
            )
    return items


def _capability_label(t, capability: str) -> str:
    normalized = str(capability or "").strip()
    if not normalized:
        return ""
    key = f"system.engine.capability.{normalized}"
    translated = t(key)
    if translated != key:
        return translated
    return normalized.replace("_", "-")


def add_provider_cards(
    builder,
    *,
    sections: dict[str, list[dict[str, Any]]],
    engine_rows: list[dict],
    container_id: str,
    t,
) -> None:
    rows_by_provider: dict[str, list[dict]] = {}
    for row in engine_rows:
        if not isinstance(row, dict):
            continue
        provider = str(row.get("provider") or "").strip().lower()
        if provider:
            rows_by_provider.setdefault(provider, []).append(row)

    for provider_rows in rows_by_provider.values():
        provider_rows.sort(key=lambda row: int(row.get("id") or 0))

    section_ids: list[str] = []
    for section_name, section_items in sorted(
        sections.items(), key=lambda item: section_sort_key(item[0])
    ):
        safe_section = section_name.replace("-", "_")
        section_card_ids: list[str] = []
        for item in section_items:
            provider = str(item.get("provider") or "").strip().lower()
            if not provider:
                continue

            provider_rows = rows_by_provider.get(provider, [])
            configurable = bool(item.get("configurable"))
            first = provider_rows[0] if provider_rows else {}
            instance_id = (
                int(first["id"])
                if isinstance(first, dict) and first.get("id")
                else None
            )
            if configurable:
                route = f"/system/engine/provider/{provider}"
            else:
                route = (
                    f"/system/engine/instance/{instance_id}/view" if instance_id else ""
                )

            count_value = max(0, int(item.get("engine_count") or 0))
            status = str(item.get("status") or "uninstalled")
            safe_provider = provider.replace("-", "_")
            wrapper_id = f"engine_provider_{safe_provider}_wrap"
            card_id = f"engine_provider_{safe_provider}_card"
            section_card_ids.append(wrapper_id)

            meta_badges = [
                sdk.ui.Badge(
                    f"{card_id}_section",
                    section_title(t, section_name),
                    variant="secondary",
                ),
                sdk.ui.Badge(
                    f"{card_id}_status",
                    provider_status_label(t, status),
                    variant=provider_status_variant(status),
                ),
            ]
            if configurable:
                meta_badges.append(
                    sdk.ui.Badge(
                        f"{card_id}_count",
                        t(
                            "system.engine.list.engine_count",
                            context={"count": count_value},
                        ),
                        variant="secondary",
                    )
                )

            capability_badges = []
            for idx, capability in enumerate(item.get("capabilities") or []):
                label = _capability_label(t, str(capability))
                if not label:
                    continue
                capability_badges.append(
                    sdk.ui.Badge(
                        f"{card_id}_capability_{idx}",
                        label,
                        variant="info",
                    )
                )

            image = sdk.ui.Image(
                f"{card_id}_icon",
                str(item.get("title") or provider),
                url=str(item.get("icon_url") or "assets/engines/llamacpp.png"),
                width=48,
                height=48,
            )
            image.set_property(
                "style",
                "min-width: 48px; min-height: 48px; max-width: 48px; max-height: 48px;",
            )

            header = sdk.ui.Row(
                f"{card_id}_header",
                [
                    image,
                    sdk.ui.Column(
                        f"{card_id}_identity",
                        [
                            sdk.ui.Title(
                                f"{card_id}_title",
                                str(item.get("title") or provider),
                                level=4,
                            ),
                            sdk.ui.Text(
                                f"{card_id}_description",
                                str(item.get("description") or ""),
                            ),
                        ],
                    ),
                ],
            )
            header.set_property("spacing", 12)
            header.set_property("style", "margin-bottom: 12px;")

            meta = sdk.ui.Row(f"{card_id}_meta", meta_badges)
            meta.set_property("spacing", 8)
            meta.set_property("style", "margin-bottom: 12px;")

            children = [header, meta]
            if capability_badges:
                capabilities = sdk.ui.Flow(
                    f"{card_id}_capabilities",
                    capability_badges,
                    spacing=8,
                )
                children.append(capabilities)

            actions = []
            if route:
                actions.append(
                    {
                        "label": t("system.engine.list.action.details"),
                        "icon": "ric.external-link-line",
                        "variant": "default",
                        "action": {
                            "name": "nav",
                            "context": {"type": "nav", "path": route},
                        },
                    }
                )

            card = sdk.ui.Card(
                card_id,
                children,
                variant="elevated",
                item_actions=actions,
                data={
                    "provider": provider,
                    "path": route,
                    "engine_count": count_value,
                    "configurable": configurable,
                },
            )
            card.set_property("padding", [16, 16, 16, 16])
            card_width = 720
            card.set_property(
                "style",
                f"width: {card_width}px; max-width: {card_width}px;",
            )

            wrapper = sdk.ui.Column(wrapper_id, [card])
            wrapper.set_property("width", card_width)
            wrapper.set_property("max_width", card_width)
            wrapper.set_property("style", f"max-width: {card_width}px;")
            builder.add(wrapper)

        if not section_card_ids:
            continue

        flow = sdk.ui.Flow(f"engine_provider_{safe_section}_flow", spacing=16)
        flow.set_children(section_card_ids)
        section_body = sdk.ui.FlexContainer(
            f"engine_provider_{safe_section}_body",
            [flow],
        )
        section = sdk.ui.Column(
            f"engine_provider_{safe_section}_section",
            [
                sdk.ui.Title(
                    f"engine_provider_{safe_section}_title",
                    section_title(t, section_name),
                    level=3,
                ),
                section_body,
            ],
        )
        section.set_property("style", "margin-top: 8px;")
        builder.add(section)
        section_ids.append(section.id)

    container = builder.get_component(container_id)
    if container is not None:
        container.set_children(section_ids)


def provider_status(provider_rows: list[dict[str, Any]]) -> str:
    statuses = {
        str(row.get("status") or "").strip().lower()
        for row in provider_rows
        if isinstance(row, dict)
    }
    if "active" in statuses:
        return "active"
    if "installing" in statuses:
        return "installing"
    if "error" in statuses:
        return "error"
    if "installed" in statuses:
        return "installed"
    return "uninstalled"


def provider_status_label(t, status: str) -> str:
    normalized = str(status or "").strip().lower()
    key = f"system.engine.status.{normalized}"
    translated = t(key)
    if translated != key:
        return translated
    return normalized or "unknown"


def provider_status_variant(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "active":
        return "success"
    if normalized == "installing":
        return "warning"
    if normalized == "installed":
        return "secondary"
    return "destructive"


def section_title(t, section_name: str) -> str:
    key = f"system.engine.list.section.{section_name}"
    translated = t(key)
    if translated != key:
        return translated
    return section_name.replace("_", " ").upper()
