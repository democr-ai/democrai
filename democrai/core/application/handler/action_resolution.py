from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from democrai.core.application.auth.action import (
    check_access,
    get_required_permissions,
)
from democrai.core.runtime.foundation.app import app_ctx

_LOG_SANITIZE_RE = re.compile(r"[\r\n\x1b].*", re.DOTALL)


def _sanitize_for_log(value: str) -> str:
    return _LOG_SANITIZE_RE.sub("[sanitized]", str(value))


ActionHandler = Callable[[dict, dict, Any], Awaitable[Dict[str, Any]]]


@dataclass(frozen=True)
class ResolvedAction:
    source: str
    handler: ActionHandler
    sdk: Any


def build_module_sdk(module: Any, session: dict) -> Any:
    from democrai.sdk.client import SDK as ModuleSDK

    return ModuleSDK(
        module_path=module.path,
        module_name=module.name,
        current_path=session.get("current_path", ""),
        session=session,
    )


def resolve_module_name(action_name: str) -> str | None:
    if "." not in action_name:
        return None
    return action_name.split(".")[0]


def resolve_core_action(action_name: str, core_actions: Dict[str, Callable], sdk: Any) -> ResolvedAction | None:
    handler = core_actions.get(action_name)
    if handler is None:
        return None
    return ResolvedAction(source="core", handler=handler, sdk=sdk)


def resolve_registry_action(action_name: str, session: dict, fallback_sdk: Any) -> ResolvedAction | None:
    from democrai.sdk.decorators import get_registry

    registry = get_registry()
    handler = registry.actions.get(action_name)
    if handler is None:
        return None

    active_sdk = fallback_sdk
    module_name = resolve_module_name(action_name)
    if module_name:
        module = app_ctx().modules.get_module(module_name)
        if module:
            active_sdk = build_module_sdk(module, session)

    return ResolvedAction(source="registry", handler=handler, sdk=active_sdk)


_legacy_action_cache: Dict[str, Optional[ResolvedAction]] = {}
_legacy_module_cache: Dict[str, Any] = {}
_legacy_cache_registry_id: Optional[int] = None


def resolve_legacy_action(action_name: str, session: dict) -> ResolvedAction | None:
    global _legacy_cache_registry_id
    modules = app_ctx().modules
    registry_id = id(modules)

    # Invalidate cache when the modules registry object changes (e.g. in tests or reload).
    if registry_id != _legacy_cache_registry_id:
        _legacy_action_cache.clear()
        _legacy_module_cache.clear()
        _legacy_cache_registry_id = registry_id

    if action_name in _legacy_action_cache:
        cached_module = _legacy_module_cache.get(action_name)
        if cached_module is not None:
            # Rebuild sdk with fresh session — only the handler/module is cached
            cached = _legacy_action_cache[action_name]
            return ResolvedAction(source=cached.source, handler=cached.handler,
                                  sdk=build_module_sdk(cached_module, session))
        return _legacy_action_cache[action_name]

    for module in modules.get_all_modules():
        if module.actions_module and hasattr(module.actions_module, action_name):
            result = ResolvedAction(
                source="legacy",
                handler=getattr(module.actions_module, action_name),
                sdk=build_module_sdk(module, session),
            )
            _legacy_action_cache[action_name] = result
            _legacy_module_cache[action_name] = module
            return result

    _legacy_action_cache[action_name] = None
    return None


def invalidate_legacy_action_cache(module_name: str | None = None) -> None:
    """Call on module reload. Pass module_name to invalidate selectively."""
    if module_name is None:
        _legacy_action_cache.clear()
        _legacy_module_cache.clear()
    else:
        prefix = f"{module_name}."
        keys = [k for k in _legacy_action_cache if k == module_name or k.startswith(prefix)]
        for k in keys:
            _legacy_action_cache.pop(k, None)
            _legacy_module_cache.pop(k, None)


def check_action_permissions(action_name: str, handler: Callable, permissions: List[str]) -> dict | None:
    required = get_required_permissions(handler)
    if check_access(required, permissions):
        return None
    app_ctx().logger.warning(
        f"[Dispatcher] Access Denied for '{_sanitize_for_log(action_name)}' (requires: {required})"
    )
    return {
        "ok": False,
        "type": "error",
        "error": "permission_denied",
        "details": f"Missing one of: {required}",
    }


def unknown_action_response(action_name: str) -> dict:
    app_ctx().logger.warning(f"[Dispatcher] Unknown action: {_sanitize_for_log(action_name)}")
    return {
        "ok": False,
        "type": "error",
        "error": "unknown_action",
        "details": action_name,
    }


def action_execution_error(action_name: str, exc: Exception, *, source: str) -> dict:
    import traceback

    app_ctx().logger.error(
        f"[Dispatcher] Error executing {source} action {_sanitize_for_log(action_name)}: {exc}\n{traceback.format_exc()}"
    )
    return {
        "effects": [
            {
                "type": "notify",
                "channel": "toast",
                "payload": {
                    "level": "error",
                    "message": "An error occurred while executing the action.",
                },
                "user_id": None,
                "organization_id": None,
            }
        ]
    }
