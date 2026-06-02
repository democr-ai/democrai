from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from democrai.core.runtime.foundation.app import app_ctx


_VALIDATION_ATTR = "_democrai_action_validation"
_CORE_CONTEXT_KEYS = frozenset({"_surface_id", "_source_component_id", "stream_id", "session_key"})


@dataclass(frozen=True)
class ActionValidation:
    schema: type[BaseModel]
    strip_extra: bool


def set_action_validation(
    func: Any,
    *,
    schema: type[BaseModel],
    strip_extra: bool = False,
) -> Any:
    if not isinstance(schema, type) or not issubclass(schema, BaseModel):
        raise TypeError("action validation schema must be a pydantic BaseModel class")
    setattr(func, _VALIDATION_ATTR, ActionValidation(schema=schema, strip_extra=bool(strip_extra)))
    return func


def get_action_validation(func: Any) -> ActionValidation | None:
    config = getattr(func, _VALIDATION_ATTR, None)
    return config if isinstance(config, ActionValidation) else None


def validate_action_ctx(action_name: str, ctx: dict[str, Any], config: ActionValidation) -> tuple[dict[str, Any] | None, str | None]:
    schema_fields = config.schema.model_fields
    validation_input = {key: ctx[key] for key in schema_fields if key in ctx}
    try:
        model = config.schema.model_validate(validation_input)
    except ValidationError as exc:
        error_text = _validation_message(exc)
        app_ctx().logger.warning(
            f"[ActionValidation] Invalid action payload action={action_name} schema={config.schema.__name__} error={error_text}"
        )
        return None, error_text

    validated = model.model_dump()
    if config.strip_extra:
        runtime_context = {key: ctx[key] for key in _CORE_CONTEXT_KEYS if key in ctx}
        return {**validated, **runtime_context}, None

    merged = dict(ctx)
    merged.update(validated)
    return merged, None


def validation_error_response(sdk: Any, error_text: str) -> dict[str, Any]:
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [
                {
                    "eventNotification": {
                        "kind": "toast",
                        "variant": "error",
                        "title": "Invalid action payload",
                        "text": error_text,
                    }
                }
            ]
        )
    )


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Payload validation failed."
    first = errors[0]
    loc = ".".join(str(item) for item in first.get("loc", ())) or "payload"
    message = str(first.get("msg") or "Invalid value")
    return f"{loc}: {message}"
