from __future__ import annotations

from typing import Any


def summarize_log_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": "dict",
            "keys": sorted(str(key) for key in value.keys()),
        }
    if isinstance(value, list):
        return {"type": "list", "items": len(value)}
    if isinstance(value, tuple):
        return {"type": "tuple", "items": len(value)}
    if isinstance(value, str):
        return {"type": "str", "chars": len(value)}
    if isinstance(value, bytes):
        return {"type": "bytes", "bytes": len(value)}
    if value is None:
        return {"type": "none"}
    return {"type": type(value).__name__}
