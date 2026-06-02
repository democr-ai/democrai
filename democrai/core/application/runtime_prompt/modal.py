from __future__ import annotations

from democrai.sdk.ui import Builder, ui

from democrai.core.application.runtime_prompt.models import RuntimePromptRequest


def _candidate_label(item) -> str:
    if isinstance(item, dict):
        model = str(item.get("model") or "").strip()
        engine = str(item.get("engine_id") or "").strip()
        if model and engine:
            return f"{model} ({engine})"
        if model:
            return model
        if engine:
            return engine
    return str(item).strip()


def _resource_swap_description(request: RuntimePromptRequest) -> str:
    metadata = request.metadata or {}
    if metadata.get("kind") != "engine_resource_swap":
        return ""
    model_to_load = str(metadata.get("model_to_load") or "").strip()
    to_unload = [_candidate_label(item) for item in (metadata.get("to_unload") or [])]
    to_unload = [item for item in to_unload if item]
    lines = []
    if model_to_load:
        lines.append(f"Requested model: {model_to_load}")
    if to_unload:
        lines.append("Models to unload:")
        lines.extend(f"- {item}" for item in to_unload)
    else:
        lines.append("No active model candidates are available for unloading.")
    return "\n".join(lines)


def _title(request: RuntimePromptRequest) -> str:
    if (request.metadata or {}).get("kind") == "engine_resource_swap":
        return "AI resource confirmation"
    return "Confirmation required"


def build_runtime_prompt_drawer_messages(request: RuntimePromptRequest) -> list[dict]:
    builder = Builder()
    question_id = f"runtime_prompt_{request.prompt_id}_question"
    details_id = f"runtime_prompt_{request.prompt_id}_details"
    actions_id = f"runtime_prompt_{request.prompt_id}_actions"
    form_id = f"runtime_prompt_{request.prompt_id}_form"
    body_id = f"runtime_prompt_{request.prompt_id}_body"

    builder.add(
        ui.Alert(
            question_id,
            _title(request),
            request.question,
            variant="warning",
        )
    )

    body_children = [question_id]
    description = _resource_swap_description(request)
    if description:
        builder.add(ui.Text(details_id, description))
        body_children.append(details_id)

    submit_action = request.actions[0]
    for action in request.actions:
        if action.id == "submit":
            submit_action = action
            break

    if request.form_model:
        builder.add(
            ui.Form(
                form_id,
                model=[dict(item) for item in request.form_model],
                values=dict(request.form_values or {}),
                submit_label=submit_action.label,
                action="runtime_prompt_response",
                params={
                    "prompt_id": request.prompt_id,
                    "action": submit_action.id,
                },
                track_loading="runtime_prompt_response",
            )
        )
        body_children.append(form_id)

    action_buttons = []
    for action in request.actions:
        if request.form_model and action.id == submit_action.id:
            continue
        button_id = f"runtime_prompt_{request.prompt_id}_action_{action.id}"
        action_buttons.append(button_id)
        builder.add(
            ui.Button(
                button_id,
                action.label,
                action="runtime_prompt_response",
                params={
                    "prompt_id": request.prompt_id,
                    "action": action.id,
                },
                variant="primary" if action.id != "deny" else "secondary",
            )
        )

    if action_buttons:
        builder.add(ui.Row(actions_id, action_buttons))
        body_children.append(actions_id)
    body = ui.Column(body_id, body_children)
    body.set_prop("spacing", 16)
    body.set_prop("style", "min-width: 720px;")
    builder.add(body)

    messages = list(builder.build_surface_update_payload("drawer"))
    messages.append(
        {
            "beginRendering": {
                "root": body_id,
                "surfaceId": "drawer",
                "options": {"position": "right", "dim": 820},
            }
        }
    )
    return messages
