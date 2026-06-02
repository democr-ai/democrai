from __future__ import annotations

from typing import Any

from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.application.runtime_prompt.grpc.client import RuntimePromptClient
from democrai.core.platform.agents.registry import agent_tool_registry
from democrai.core.platform.agents.skill_scripts import run_skill_script
from democrai.core.runtime.foundation.app import current_request_context_payload


FORM_FIELD_TYPES = (
    "text",
    "email",
    "password",
    "number",
    "integer",
    "int",
    "float",
    "decimal",
    "textarea",
    "checkbox",
    "check",
    "radio",
    "radio_group",
    "select",
    "file",
    "attachment",
    "audio_recorder",
    "tags",
    "tags_input",
    "editable_list",
    "date",
    "datetime",
    "date_time",
    "toggle",
    "switch",
)
FORM_MODEL_TYPES = FORM_FIELD_TYPES


def _validate_form_model(model: Any) -> list[str]:
    if not isinstance(model, list):
        return ["form_model_must_be_array"]
    errors: list[str] = []
    for index, item in enumerate(model):
        _validate_form_node(item, f"form_model[{index}]", errors)
    return errors


def _validate_form_node(node: Any, path: str, errors: list[str]) -> None:
    if not isinstance(node, dict):
        errors.append(f"{path}: node_must_be_object")
        return
    raw_field_type = node.get("type")
    if raw_field_type is None:
        field_type = "text"
    elif isinstance(raw_field_type, str):
        field_type = raw_field_type.strip().lower()
    else:
        field_type = ""
    if field_type not in FORM_MODEL_TYPES:
        errors.append(
            f"{path}: unsupported_type={field_type}; use one of {', '.join(FORM_MODEL_TYPES)}"
        )
        return
    raw_name = node.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        errors.append(f"{path}: field_name_required")
    if field_type in {"select", "radio", "radio_group"} and not isinstance(
        node.get("options"),
        list,
    ):
        errors.append(f"{path}: options_array_required_for_{field_type}")


async def ask_user(
    question: str,
    form_model: list[dict[str, Any]],
    values: dict[str, Any] | None = None,
    submit_label: str = "Submit",
    timeout_seconds: float = 60.0,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ask the current interactive user for structured input."""
    form_errors = _validate_form_model(form_model)
    if form_errors:
        return {
            "ok": False,
            "error": "invalid_form_model",
            "details": form_errors,
            "allowed_field_types": list(FORM_FIELD_TYPES),
            "hint": (
                "Use a flat form_model list of field nodes only. "
                "Use type='select' for dropdown fields. "
                "Nested row/column layouts and type='dropdown' are not supported."
            ),
        }

    request_context = current_request_context_payload("core.ask-user")
    if not request_context:
        return {"ok": False, "error": "runtime_prompt_request_context_required"}

    resolved_submit_label = (
        submit_label if isinstance(submit_label, str) and submit_label else "Submit"
    )
    tool_context = {} if context is None else dict(context)
    timeout = float(timeout_seconds)
    actions = [
        {"id": "submit", "label": resolved_submit_label},
        {"id": "cancel", "label": "Cancel"},
    ]
    metadata = {
        "kind": "agent_hitl_form",
        "caller_context": tool_context,
    }
    client = RuntimePromptClient(timeout=timeout + 5.0)
    resolved_question = question if isinstance(question, str) else ""
    resolved_form_model = list(form_model)
    resolved_values = {} if values is None else dict(values)
    try:
        async with ai_pipeline_step(
            type="runtime_prompt",
            name="agent_hitl_form",
            input={
                "question": resolved_question,
                "form_model": resolved_form_model,
                "metadata": metadata,
            },
        ) as step:
            decision = await client.ask(
                question=resolved_question,
                actions=actions,
                form_model=resolved_form_model,
                form_values=resolved_values,
                request_context=request_context,
                metadata=metadata,
                timeout_seconds=timeout,
            )
            payload = decision.to_dict()
            if decision.action == "cancel":
                payload["ok"] = False
                payload["error"] = "runtime_prompt_cancelled"
            if isinstance(step, dict):
                step["output"] = payload
                if not decision.ok or decision.action == "cancel":
                    step["status"] = "denied" if decision.action == "cancel" else "error"
            return payload
    finally:
        await client.close()


agent_tool_registry.register(
    "core.run-skill-script",
    run_skill_script,
    title="Run skill script",
    description="Run a Python script provided by an activated skill in a restricted sandbox.",
    input_schema={
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "description": "Fully qualified skill name.",
            },
            "script": {
                "type": "string",
                "description": "Script path relative to the skill scripts directory.",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Command line arguments for the script.",
            },
            "timeout_seconds": {
                "type": "number",
                "description": "Execution timeout in seconds.",
            },
        },
        "required": ["skill", "script"],
    },
    module_name="core",
    user_selectable=False,
)

agent_tool_registry.register(
    "core.ask-user",
    ask_user,
    title="Ask user",
    description=(
        "Ask the current chat user for structured input using a UI form. "
        "Use this when required values should come from the user instead of being guessed. "
        "The form_model must be a flat list of fields only. "
        "For dropdown fields use type='select' with an options array; type='dropdown' is not supported."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Question shown above the form.",
            },
            "form_model": {
                "type": "array",
                "description": (
                    "Form model supported by the UI Form component. Field type must be "
                    "one of the enum values. Use select for dropdowns."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": list(FORM_MODEL_TYPES),
                            "description": (
                                "Flat field type. Use select for dropdown fields; "
                                "row, column, and dropdown are not valid."
                            ),
                        },
                        "name": {
                            "type": "string",
                            "description": "Required for every field.",
                        },
                        "label": {"type": "string"},
                        "placeholder": {"type": "string"},
                        "options": {
                            "type": "array",
                            "description": "Required for select, radio, and radio_group fields.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "value": {},
                                },
                                "required": ["label", "value"],
                            },
                        },
                        "multiple": {"type": "boolean"},
                    },
                    "required": ["type", "name"],
                    "additionalProperties": True,
                },
            },
            "values": {
                "type": "object",
                "description": "Initial form values keyed by field name.",
            },
            "submit_label": {
                "type": "string",
                "description": "Submit button label.",
            },
            "timeout_seconds": {
                "type": "number",
                "description": "How long to wait for the user response.",
            },
        },
        "required": ["question", "form_model"],
    },
    module_name="core",
    user_selectable=False,
)
