from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.ui.form_models.organization import (
    build_organization_form_model,
)
from modules.system.utils.ui.user.render import resolve_route_id, set_title_text


async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/organization/update")
    organization_id = resolve_route_id(params)
    form = builder.get_component("organization_update_form")
    title = builder.get_component("organization_update_title")

    if organization_id is None:
        set_title_text(title, sdk.i18n.t("system.organization.update.invalid_id"))
        if form is not None:
            form.set_property("model", [])
        return builder

    organization = sdk.models.organizations.view(organization_id)
    if organization is None:
        set_title_text(
            title,
            sdk.i18n.t(
                "system.organization.update.not_found",
                context={"organization_id": organization_id},
            ),
        )
        if form is not None:
            form.set_property("model", [])
        return builder

    set_title_text(
        title,
        sdk.i18n.t(
            "system.organization.update.title",
            context={"name": str(organization.get("name") or "")},
        ),
    )
    if form is not None:
        form.set_property(
            "model",
            build_organization_form_model(
                sdk.i18n.t,
                defaults={
                    "name": organization.get("name"),
                    "description": organization.get("description"),
                },
            ),
        )
        form.set_property(
            "action",
            {
                "name": "system.update_organization",
                "context": {"organization_id": organization_id},
            },
        )

    return builder
