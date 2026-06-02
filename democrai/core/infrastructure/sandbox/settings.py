from __future__ import annotations

import os


SANDBOX_RUNTIME_MODE_PYTHON_IN_PROCESS = "python_in_process"

_VALID_RUNTIME_MODES = {
    SANDBOX_RUNTIME_MODE_PYTHON_IN_PROCESS,
}
_runtime_mode = SANDBOX_RUNTIME_MODE_PYTHON_IN_PROCESS


def _normalize_runtime_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _VALID_RUNTIME_MODES:
        return normalized
    return SANDBOX_RUNTIME_MODE_PYTHON_IN_PROCESS


def get_sandbox_runtime_mode() -> str:
    env_value = str(os.environ.get("DEMOCRAI_SANDBOX_RUNTIME_MODE") or "").strip()
    if env_value:
        return _normalize_runtime_mode(env_value)
    return _runtime_mode


def set_sandbox_runtime_mode(value: str | None) -> str:
    global _runtime_mode
    _runtime_mode = _normalize_runtime_mode(value)
    return _runtime_mode
