from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.ui.form_models.role import (
    build_role_form_model,
)
from modules.system.utils.ui.user.render import resolve_route_id, set_title_text


async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/roles/update")
    role_id = resolve_route_id(params)

    form = builder.get_component("role_update_form")
    title = builder.get_component("role_update_title")

    if role_id is None:
        set_title_text(title, sdk.i18n.t("system.role.update.invalid_id"))
        if form is not None:
            form.set_property("model", [])
        return builder

    role = sdk.models.roles.view(role_id)
    if role is None:
        set_title_text(
            title,
            sdk.i18n.t("system.role.update.not_found", context={"role_id": role_id}),
        )
        if form is not None:
            form.set_property("model", [])
        return builder

    defaults = {
        "name": role.get("name"),
        "description": role.get("description"),
    }

    set_title_text(
        title,
        sdk.i18n.t(
            "system.role.update.title",
            context={"name": str(role.get("name") or "")},
        ),
    )

    if form is not None:
        model = build_role_form_model(
            t=sdk.i18n.t,
            defaults=defaults,
        )
        form.set_property("model", model)
        form.set_property(
            "action",
            {
                "name": "system.update_role",
                "context": {"role_id": role_id},
            },
        )

    return builder
