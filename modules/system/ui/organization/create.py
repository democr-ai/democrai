from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.ui.form_models.organization import (
    build_organization_form_model,
)


async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/organization/create")
    form = builder.get_component("organization_create_form")
    if form is not None:
        form.set_property("model", build_organization_form_model(sdk.i18n.t))
    return builder
