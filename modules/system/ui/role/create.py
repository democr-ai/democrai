from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.ui.form_models.role import (
    build_role_form_model,
)


async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/roles/create")
    form = builder.get_component("role_create_form")

    if form is not None:
        model = build_role_form_model(
            t=sdk.i18n.t,
            defaults={},
        )
        form.set_property("model", model)

    return builder
