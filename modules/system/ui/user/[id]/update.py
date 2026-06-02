from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.ui.form_models.user.user import (
    build_user_form_model,
    user_role_options,
)
from modules.system.utils.ui.user.render import resolve_route_id, set_title_text


async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/user/update")
    user_id = resolve_route_id(params)

    form = builder.get_component("user_update_form")
    title = builder.get_component("user_update_title")

    if user_id is None:
        set_title_text(title, sdk.i18n.t("system.user.update.invalid_id"))
        if form is not None:
            form.set_property("model", [])
        return builder

    user = sdk.models.users.view(user_id)
    if user is None:
        set_title_text(
            title,
            sdk.i18n.t("system.user.update.not_found", context={"user_id": user_id}),
        )
        if form is not None:
            form.set_property("model", [])
        return builder

    defaults = {
        "username": user.get("username"),
        "email": user.get("email"),
        "role": user.get("role"),
        "access_level": user.get("access_level"),
    }

    set_title_text(
        title,
        sdk.i18n.t(
            "system.user.update.title",
            context={"username": str(user.get("username") or "")},
        ),
    )

    if form is not None:
        model = build_user_form_model(
            user_role_options(sdk),
            t=sdk.i18n.t,
            include_password=False,
            defaults=defaults,
        )
        form.set_property("model", model)
        form.set_property(
            "action",
            {
                "name": "system.update_user",
                "context": {"user_id": user_id},
            },
        )

    return builder
