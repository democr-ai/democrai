from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.ui.form_models.user.user import (
    build_user_form_model,
    user_role_options,
)
from modules.system.utils.ui.user.render import resolve_route_id


async def render(params: dict, session: dict):
    organization_id = resolve_route_id(params)
    builder = sdk.ui.load("utils/ui/yaml/user/create")
    title = builder.get_component("user_create_title")
    form = builder.get_component("user_create_form")

    if title is not None:
        title.set_property(
            "text",
            {"literalString": sdk.i18n.t("system.organization.users.create.title")},
        )

    if form is not None:
        model = build_user_form_model(
            user_role_options(sdk),
            t=sdk.i18n.t,
            include_password=True,
        )
        form.set_property("model", model)
        form.set_property(
            "submit_label",
            sdk.i18n.t("system.organization.users.create.submit"),
        )
        form.set_property(
            "action",
            {
                "name": "system.create_organization_user",
                "context": {"organization_id": organization_id},
            },
        )

    return builder
