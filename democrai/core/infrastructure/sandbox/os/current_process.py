from __future__ import annotations

import sys
from typing import Any


def is_os_sandbox_enabled(config: Any = None) -> bool:
    resolved = _resolve_config(config)
    getter = getattr(resolved, "get", None)
    if not callable(getter):
        return False
    return bool(getter("sandbox.os.enabled", False))


def apply_current_process_os_sandbox(config: Any = None) -> dict[str, Any]:
    resolved = _resolve_config(config)
    if not is_os_sandbox_enabled(resolved):
        return _skipped_status(reason="disabled")
    provider = _current_provider()
    return provider.apply_current_process_os_sandbox(resolved)


def get_current_process_os_sandbox_status(config: Any = None) -> dict[str, Any]:
    resolved = _resolve_config(config)
    provider = _current_provider()
    status = provider.get_current_process_os_sandbox_status(resolved)
    return {
        "enabled": is_os_sandbox_enabled(resolved),
        "platform": sys.platform,
        **status,
    }


def _current_provider():
    from democrai.core.infrastructure.sandbox.os.factory import get_os_sandbox_provider

    return get_os_sandbox_provider()


def _resolve_config(config: Any) -> Any:
    if config is not None:
        return config
    try:
        from democrai.core.runtime.foundation.app import app_ctx
        return app_ctx().config
    except Exception:
        return None


def _skipped_status(*, reason: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "provider": _current_provider().__class__.__name__,
        "platform": sys.platform,
        "applied": False,
        "skipped": True,
        "error": None,
        "reason": reason,
        "details": {},
    }
