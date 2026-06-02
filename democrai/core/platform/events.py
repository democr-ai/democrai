from __future__ import annotations

import inspect
from typing import Any

from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.registry import (
    ModuleEventDefinition,
    ModuleEventRegistration,
    module_event_registry,
)


def _event_warning(message: str) -> None:
    logger = app_ctx().logger
    if logger is not None:
        logger.warning(message, "event")


def _event_error(message: str) -> None:
    logger = app_ctx().logger
    if logger is not None:
        logger.error(message, "event")


def _build_event_sdk(registration: ModuleEventRegistration, session: dict):
    from democrai.sdk.client import SDK as ModuleSDK

    module_name = (
        registration.module_name
        if isinstance(registration.module_name, str) and registration.module_name
        else "core"
    )
    raw_current_path = session.get("current_path") if isinstance(session, dict) else None
    current_path = raw_current_path if isinstance(raw_current_path, str) else ""

    if module_name == "core":
        return ModuleSDK("", "core", current_path=current_path, session=session)

    module = app_ctx().modules.get_module(module_name)
    if module is None:
        raise RuntimeError(
            f"Module event '{registration.name}' references unknown module '{module_name}'"
        )

    return ModuleSDK(
        module_path=module.path,
        module_name=module.name,
        current_path=current_path,
        session=session,
    )


async def _invoke_event_listener(
    registration: ModuleEventRegistration,
    *,
    event_name: str,
    payload: dict[str, Any],
    session: dict,
    event_sdk: Any,
) -> Any:
    from democrai.sdk.client import current_sdk as _current_module_sdk

    sig = inspect.signature(registration.func)
    call_args: dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        if param_name == "payload":
            call_args[param_name] = payload
        elif param_name == "session":
            call_args[param_name] = session
        elif param_name in {"sdk", "module_sdk", "democrai_sdk"}:
            call_args[param_name] = event_sdk
        elif param_name == "event_name":
            call_args[param_name] = event_name
        elif param_name in payload:
            call_args[param_name] = payload[param_name]
        elif param.default is not inspect.Parameter.empty:
            call_args[param_name] = param.default

    token = _current_module_sdk.set(event_sdk)
    try:
        result = registration.func(**call_args)
        if inspect.isawaitable(result):
            result = await result
        return result
    except Exception as exc:
        _event_error(
            f"Error while executing module event '{event_name}' for listener module "
            f"'{registration.module_name}': {exc}"
        )
        return None
    finally:
        _current_module_sdk.reset(token)


def _validate_event_payload(
    event_name: str,
    payload: dict[str, Any],
    definition: ModuleEventDefinition | None,
) -> None:
    if definition is None:
        _event_warning(
            f"Module event '{event_name}' was emitted but is not declared as a public module API"
        )
        return

    declared = set(definition.params)
    received = set(payload.keys())
    missing = sorted(declared - received)
    extra = sorted(received - declared)

    if missing:
        _event_warning(
            f"Module event '{event_name}' emitted without declared params: {', '.join(missing)}"
        )
    if extra:
        _event_warning(
            f"Module event '{event_name}' emitted with undeclared params: {', '.join(extra)}"
        )


def _log_missing_event_listeners(
    event_name: str,
    definition: ModuleEventDefinition | None,
) -> None:
    if definition is None:
        _event_warning(f"No module event listeners registered for undeclared key '{event_name}'")
        return

    if definition.optional:
        return

    _event_warning(
        f"Expected module event listeners for key '{event_name}' but none are registered"
    )


async def emit_module_event(
    name: str,
    *,
    payload: dict[str, Any] | None = None,
    session: dict | None = None,
) -> list[Any]:
    event_payload = {} if payload is None else payload
    event_session = {} if session is None else session
    definition = module_event_registry.get_definition(name)
    registrations = module_event_registry.get(name)
    results: list[Any] = []

    _validate_event_payload(name, event_payload, definition)

    if not registrations:
        _log_missing_event_listeners(name, definition)
        return results

    for registration in registrations:
        try:
            event_sdk = _build_event_sdk(registration, event_session)
        except RuntimeError as exc:
            _event_error(str(exc))
            continue
        result = await _invoke_event_listener(
            registration,
            event_name=name,
            payload=event_payload,
            session=event_session,
            event_sdk=event_sdk,
        )
        results.append(result)

    return results
