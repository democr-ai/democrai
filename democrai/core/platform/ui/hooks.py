from __future__ import annotations

import copy
import inspect
from typing import Any

from democrai.sdk.ui import Builder
from democrai.sdk.components.base import Component
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.registry import (
    RenderHookDefinition,
    RenderHookRegistration,
    render_hook_registry,
)


def _hook_warning(message: str) -> None:
    logger = app_ctx().logger
    if logger is not None:
        logger.warning(message, "hook")


def _hook_error(message: str) -> None:
    logger = app_ctx().logger
    if logger is not None:
        logger.error(message, "hook")


def _build_hook_sdk(registration: RenderHookRegistration, session: dict):
    from democrai.sdk.client import SDK as ModuleSDK

    module_name = registration.module_name or "core"
    current_path = session.get("current_path", "") if isinstance(session, dict) else ""

    if module_name == "core":
        return ModuleSDK("", "core", current_path=current_path, session=session)

    module = app_ctx().modules.get_module(module_name)
    if module is None:
        raise RuntimeError(
            f"Render hook '{registration.name}' references unknown module '{module_name}'"
        )

    return ModuleSDK(
        module_path=module.path,
        module_name=module.name,
        current_path=current_path,
        session=session,
    )


async def _invoke_hook_callback(
    registration: RenderHookRegistration,
    *,
    params: dict[str, Any],
    session: dict,
    hook_sdk: Any,
) -> Any:
    from democrai.sdk.client import current_sdk as _current_module_sdk

    sig = inspect.signature(registration.func)
    call_args: dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        if param_name == "params":
            call_args[param_name] = params
        elif param_name == "session":
            call_args[param_name] = session
        elif param_name in {"sdk", "module_sdk", "democrai_sdk"}:
            call_args[param_name] = hook_sdk
        elif param_name == "hook_name":
            call_args[param_name] = registration.name
        elif param.default is not inspect.Parameter.empty:
            call_args[param_name] = param.default

    token = _current_module_sdk.set(hook_sdk)
    try:
        result = registration.func(**call_args)
        if inspect.isawaitable(result):
            result = await result
        return result
    except Exception as exc:
        _hook_error(
            f"Error while executing render hook '{registration.name}' from module "
            f"'{registration.module_name}': {exc}"
        )
        return None
    finally:
        _current_module_sdk.reset(token)


def _prefix_component_tree_ids(
    component: Component,
    prefix: str,
    component_map: dict[str, Component] | None = None,
) -> Component:
    cloned = copy.deepcopy(component)

    def apply(node: Component):
        original_id = node.id
        node.id = f"{prefix}_{original_id}" if original_id else original_id

        new_children: list[Any] = []
        for child in node.children:
            if isinstance(child, Component):
                apply(child)
                new_children.append(child)
                continue
            if isinstance(child, str):
                if component_map and child in component_map:
                    embedded = copy.deepcopy(component_map[child])
                    apply(embedded)
                    new_children.append(embedded)
                else:
                    new_children.append(f"{prefix}_{child}")
                continue
            new_children.append(child)
        node.children = new_children

    apply(cloned)
    return cloned


def _normalize_hook_result(
    result: Any,
    registration: RenderHookRegistration,
) -> list[Component]:
    prefix = registration.module_name or "core"
    if result is None:
        return []
    if isinstance(result, Component):
        return [_prefix_component_tree_ids(result, prefix)]
    if isinstance(result, Builder):
        component_map = {
            component.id: component
            for component in result._components
            if isinstance(component, Component) and component.id
        }
        roots = result.get_roots()
        return [
            _prefix_component_tree_ids(component, prefix, component_map)
            for component in roots
            if isinstance(component, Component)
        ]
    if isinstance(result, (list, tuple)):
        normalized: list[Component] = []
        for item in result:
            if isinstance(item, Component):
                normalized.append(_prefix_component_tree_ids(item, prefix))
                continue
            raise TypeError(
                "Render hook lists must contain only Component instances"
            )
        return normalized
    raise TypeError(
        "Render hook callbacks must return Component, list[Component], Builder, or None"
    )


async def resolve_render_hook_components(
    name: str,
    *,
    params: dict[str, Any] | None = None,
    session: dict | None = None,
) -> list[Component]:
    hook_params = {} if params is None else params
    hook_session = session if session is not None else {}  # None is valid: hook called without session context
    definition = render_hook_registry.get_definition(name)
    registrations = render_hook_registry.get(name)
    resolved: list[Component] = []

    if definition is None:
        _hook_warning(
            f"Render hook slot '{name}' was resolved but is not declared as a public hook API",
        )

    if not registrations:
        _log_missing_hook_callbacks(name, definition)
        return resolved

    for registration in registrations:
        try:
            hook_sdk = _build_hook_sdk(registration, hook_session)
        except RuntimeError as exc:
            _hook_error(str(exc))
            continue
        result = await _invoke_hook_callback(
            registration,
            params=hook_params,
            session=hook_session,
            hook_sdk=hook_sdk,
        )
        resolved.extend(_normalize_hook_result(result, registration))

    return resolved


def _log_missing_hook_callbacks(
    name: str,
    definition: RenderHookDefinition | None,
) -> None:
    if definition is None:
        _hook_warning(f"No render hook callbacks registered for undeclared key '{name}'")
        return

    if definition.optional:
        return

    _hook_warning(f"Expected render hook callbacks for key '{name}' but none are registered")
