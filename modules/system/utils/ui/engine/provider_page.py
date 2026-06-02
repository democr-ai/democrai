from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk


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


def capability_label(t, capability: str) -> str:
    normalized = str(capability or "").strip()
    if not normalized:
        return ""
    key = f"system.engine.capability.{normalized}"
    translated = t(key)
    if translated != key:
        return translated
    return normalized.replace("_", "-")


def provider_engine_rows(listing: dict | None, t) -> list[dict]:
    provider_engines = list((listing or {}).get("rows") or [])
    rows: list[dict] = []
    for item in provider_engines:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "uninstalled")
        rows.append(
            {
                "id": item.get("id"),
                "engine_id": item.get("id"),
                "title": str(item.get("name") or item.get("provider") or ""),
                "text": str(item.get("provider") or ""),
                "provider": str(item.get("provider") or ""),
                "status": status,
                "status_label": provider_status_label(t, status),
                "status_variant": provider_status_variant(status),
                "route": f"/system/engine/instance/{item.get('id')}/view",
            }
        )
    return rows


def provider_engine_cards(rows: list[dict], t) -> list[dict]:
    cards: list[dict] = []
    for item in rows:
        engine_id = item.get("engine_id") or item.get("id")
        if not engine_id:
            continue
        safe_id = str(engine_id).replace("-", "_")
        card = sdk.ui.Card(
            f"engine_provider_instance_{safe_id}_card",
            [
                sdk.ui.Column(
                    f"engine_provider_instance_{safe_id}_body",
                    [
                        sdk.ui.Title(
                            f"engine_provider_instance_{safe_id}_title",
                            str(item.get("title") or ""),
                            level=4,
                        ),
                        sdk.ui.Text(
                            f"engine_provider_instance_{safe_id}_provider",
                            str(item.get("provider") or ""),
                        ),
                        sdk.ui.Row(
                            f"engine_provider_instance_{safe_id}_meta",
                            [
                                sdk.ui.Badge(
                                    f"engine_provider_instance_{safe_id}_status",
                                    str(item.get("status_label") or ""),
                                    variant=str(item.get("status_variant") or "secondary"),
                                )
                            ],
                        ),
                    ],
                )
            ],
            variant="elevated",
            item_actions=[
                {
                    "label": t("system.engine.provider.instances.action.open"),
                    "icon": "ric.external-link-line",
                    "variant": "primary",
                    "action": {
                        "name": "nav",
                        "context": {
                            "type": "nav",
                            "path": str(item.get("route") or ""),
                        },
                    },
                },
                {
                    "label": t("system.engine.provider.instances.action.edit"),
                    "icon": "ric.edit-line",
                    "variant": "secondary",
                    "action": {
                        "name": "open_drawer",
                        "context": {
                            "path": (
                                f"/system/engine/provider/config/{str(item.get('provider') or '').strip().lower()}"
                                f"?engine_id={engine_id}"
                            ),
                            "position": "right",
                            "dim": 620,
                        },
                    },
                },
                {
                    "label": t("system.engine.provider.page.action.delete"),
                    "icon": "ric.delete-bin-2-line",
                    "variant": "danger",
                    "action": {
                        "name": "system.delete_engine",
                        "context": {
                            "engine_id": engine_id,
                            "provider": str(item.get("provider") or ""),
                        },
                    },
                },
            ],
            data={
                "engine_id": engine_id,
                "provider": str(item.get("provider") or ""),
            },
        )
        card.set_property("padding", [16, 16, 16, 16])
        card.set_property("style", "width: 420px; max-width: 420px;")
        cards.append(card.to_dict())
    return cards


def capability_badge_text(model: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for item in (model.get("capabilities") or []):
        label = str(item or "").strip()
        if label:
            values.append(label)
    return values[:4]
