from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.actions.engine.quotas import counter_form_model


async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/engine/quota_counter_form")
    title = builder.get_component("engine_quota_counter_form_title")
    if title is not None:
        title.set_property("text", sdk.i18n.t("system.engine.quotas.counter.create.title"))
    form = builder.get_component("engine_quota_counter_form")
    if form is not None:
        form.set_property("model", counter_form_model(sdk))
        form.set_property("action", {"name": "system.create_engine_quota_counter"})
    return builder
