from __future__ import annotations

from typing import Any

from democrai.sdk.engines import (
    provider_requirements,
)


def provider_display_name(module_sdk, provider: str) -> str:
    key = f"system.engine.provider.{provider}.name"
    translated = module_sdk.i18n.t(key)
    if translated == key:
        return provider
    return translated


def default_engine_name(provider: str, module_sdk) -> str:
    listing = module_sdk.models.engine_registry.list(page=0, page_size=200, filters={})
    rows = listing.get("rows") or []
    count = 0
    normalized = str(provider or "").strip().lower()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("provider") or "").strip().lower() == normalized:
            count += 1
    if count <= 0:
        return normalized
    return f"{normalized}-{count + 1}"


def render_engine_config_modal(
    module_sdk,
    *,
    provider: str,
    provider_name: str,
    engine_id: int | None,
    initial_values: dict[str, Any],
    activate_after_save: bool,
):
    model: list[dict[str, Any]] = [
        {
            "name": "name",
            "label": module_sdk.i18n.t("system.engine.config.field.name"),
            "type": "text",
            "value": str(
                initial_values.get("name") or default_engine_name(provider, module_sdk)
            ),
            "validations": [
                {
                    "rule": "required",
                    "message": module_sdk.i18n.t(
                        "system.engine.config.field.name.required"
                    ),
                }
            ],
        }
    ]
    requirements = provider_requirements(provider_id=provider)
    for field in list(requirements.get("config_schema") or []):
        if not isinstance(field, dict):
            continue
        field_copy = dict(field)
        field_name = str(field_copy.get("name") or "").strip()
        if not field_name:
            continue
        if field_name == "name":
            continue
        if field_name in initial_values and initial_values.get(field_name) is not None:
            field_copy["value"] = initial_values.get(field_name)
        model.append(field_copy)

    model.append(
        {
            "name": "concurrency_enabled",
            "label": module_sdk.i18n.t("system.engine.config.field.concurrency_enabled"),
            "type": "checkbox",
            "value": bool(initial_values.get("concurrency_enabled", False)),
        }
    )
    model.append(
        {
            "name": "concurrency_limit",
            "label": module_sdk.i18n.t("system.engine.config.field.concurrency_limit"),
            "type": "integer",
            "value": int(initial_values.get("concurrency_limit", 4)),
            "validations": [
                {
                    "rule": "min",
                    "params": [1],
                    "message": module_sdk.i18n.t(
                        "system.engine.config.field.concurrency_limit.min"
                    ),
                }
            ],
            "show_if": {
                "conditions": [
                    {
                        "left": "$form.concurrency_enabled",
                        "op": "==",
                        "right": True,
                    }
                ]
            },
        }
    )

    submit_action = "system.save_engine_config"
    submit_label = module_sdk.i18n.t("system.engine.config.action.save")
    if activate_after_save:
        submit_action = "system.save_and_activate_engine_config"
        submit_label = module_sdk.i18n.t("system.engine.config.action.save_activate")

    builder = module_sdk.ui.load("utils/ui/yaml/engine/modals/engine_config")

    dialog = builder.get_component("engine_config_dialog")
    if dialog is not None:
        dialog.set_property(
            "title",
            module_sdk.i18n.t(
                "system.engine.config.title", context={"provider": provider_name}
            ),
        )

    subtitle = builder.get_component("engine_config_subtitle")
    if subtitle is not None:
        subtitle.set_property(
            "text",
            module_sdk.i18n.t(
                "system.engine.config.subtitle", context={"provider": provider_name}
            ),
        )

    form = builder.get_component("engine_config_form")
    if form is not None:
        action_context = {
            "provider": provider,
            "engine_id": engine_id,
            "activate_after_save": activate_after_save,
        }
        form.set_property("model", model)
        form.set_property("submit_label", submit_label)
        form.set_property(
            "action",
            {
                "name": submit_action,
                "context": action_context,
            },
        )
        form.set_property("params", action_context)

    return builder


def upsert_engine_from_config(
    module_sdk,
    *,
    provider: str,
    engine_id: int | None,
    payload: dict[str, Any],
) -> int | None:
    name = str(payload.get("name") or "").strip()
    if not name:
        return None

    config = dict(payload)
    config.pop("name", None)

    if engine_id is None:
        requirements = provider_requirements(provider_id=provider)
        created = module_sdk.models.engine_registry.create(
            {
                "name": name,
                "provider": provider,
                "config": config,
                "status": "uninstalled",
                "supported": bool(requirements.get("supported")),
            }
        )
        return (
            int(created["id"]) if isinstance(created, dict) and "id" in created else None
        )

    requirements = provider_requirements(provider_id=provider)
    module_sdk.models.engine_registry.update(
        engine_id,
        {
            "name": name,
            "config": config,
            "supported": bool(requirements.get("supported")),
        },
    )
    return engine_id
