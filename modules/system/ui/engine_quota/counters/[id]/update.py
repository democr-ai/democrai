from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.actions.engine.quotas import counter_form_model
from modules.system.utils.ui.user.render import resolve_route_id


async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/engine/quota_counter_form")
    counter_id = resolve_route_id(params)
    counter = sdk.engines.get_quota_counter(counter_id=counter_id) if counter_id else None

    title = builder.get_component("engine_quota_counter_form_title")
    if title is not None:
        title.set_property(
            "text",
            sdk.i18n.t("system.engine.quotas.counter.update.title"),
        )
    form = builder.get_component("engine_quota_counter_form")
    if form is not None:
        form.set_property("model", counter_form_model(sdk, defaults=counter or {}))
        form.set_property(
            "action",
            {
                "name": "system.update_engine_quota_counter",
                "context": {"counter_id": int(counter_id or 0)},
            },
        )
    return builder
