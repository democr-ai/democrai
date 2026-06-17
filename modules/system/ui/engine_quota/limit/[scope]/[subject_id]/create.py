from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.actions.engine.quotas import limit_form_model


async def render(params: dict, session: dict):
    route_params = dict(params.get("route_params") or {})
    scope = str(route_params.get("scope") or "").strip()
    subject_id = int(route_params.get("subject_id") or 0)

    builder = sdk.ui.load("utils/ui/yaml/engine/quota_limit_form")
    title = builder.get_component("engine_quota_limit_form_title")
    if title is not None:
        title.set_property("text", sdk.i18n.t("system.engine.quotas.limit.create.title"))
    form = builder.get_component("engine_quota_limit_form")
    if form is not None:
        form_scope = "global" if scope == "global" else scope
        form.set_property("model", limit_form_model(sdk, scope=form_scope))
        form.set_property(
            "action",
            {
                "name": "system.create_engine_quota_limit",
                "context": {"scope": form_scope, "subject_id": subject_id},
            },
        )
    return builder
