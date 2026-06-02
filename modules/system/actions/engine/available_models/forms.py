from __future__ import annotations

from typing import Any


def _open_activation_drawer(
    module_sdk,
    *,
    title: str,
    form_model: list[dict[str, Any]],
    action: dict[str, Any],
    submit_label: str | None = None,
):
    builder = module_sdk.ui.load("utils/ui/yaml/engine/model_activation")
    title_component = builder.get_component("engine_model_activation_title")
    if title_component is not None:
        title_component.set_property("text", title)
    form = builder.get_component("engine_model_activation_form")
    if form is not None:
        form.set_property("model", form_model)
        form.set_property("action", action)
        form.set_property("track_loading", str(action.get("name") or ""))
        if submit_label:
            form.set_property("submit_label", submit_label)
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            module_sdk.effects.build_aux_surface_messages(builder, surface_id="drawer")
        )
    )
