from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.ui.form_models.user.password import (
    build_password_form_model,
)
from modules.system.utils.ui.user.render import resolve_route_id, set_title_text


async def render(params: dict, session: dict):

    user_id = resolve_route_id(params)
    builder = sdk.ui.load("utils/ui/yaml/user/change_password")

    title_text = sdk.i18n.t("system.user.password.title.default")
    if user_id is not None:
        user = sdk.models.users.view(user_id)
        if user is not None:
            title_text = sdk.i18n.t(
                "system.user.password.title.user",
                context={"username": str(user.get("username") or "")},
            )

    title = builder.get_component("user_change_password_title")
    set_title_text(title, title_text)

    form = builder.get_component("user_change_password_form")
    if form is not None:
        form.set_property("model", build_password_form_model(sdk.i18n.t))
        form.set_property(
            "action",
            {
                "name": "system.change_password",
                "context": {"user_id": user_id},
            },
        )

    return builder
