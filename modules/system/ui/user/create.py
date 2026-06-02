from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.ui.form_models.user.user import (
    build_user_form_model,
    user_role_options,
)


async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/user/create")
    form = builder.get_component("user_create_form")

    if form is not None:
        model = build_user_form_model(
            user_role_options(sdk),
            t=sdk.i18n.t,
            include_password=True,
            defaults={},
        )
        form.set_property("model", model)

    return builder
