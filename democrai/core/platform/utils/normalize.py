import sys
from collections.abc import Iterable
from typing import Any


TRUE_STRINGS = frozenset({"1", "true", "yes", "on", "y"})
FALSE_STRINGS = frozenset({"0", "false", "no", "off", "n", ""})


def normalize_string(value: Any, *, default: str = "", strip: bool = True) -> str:
    if value is None:
        return default
    normalized = str(value)
    if strip:
        normalized = normalized.strip()
    return normalized or default


def normalize_key(value: Any, *, default: str = "") -> str:
    return normalize_string(value, default=default).lower()


def normalize_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = normalize_key(value)
    if normalized in TRUE_STRINGS:
        return True
    if normalized in FALSE_STRINGS:
        return False
    return default


def normalize_int(value: Any, *, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_float(value: Any, *, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_string_list(value: Any, *, lower: bool = False) -> list[str]:
    if isinstance(value, str):
        items: Iterable[Any] = value.split(",")
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, dict)):
        items = value
    else:
        return []

    normalized: list[str] = []
    for item in items:
        text = normalize_string(item)
        if not text:
            continue
        normalized.append(text.lower() if lower else text)
    return normalized


def qualify_module_registry_name(
    module_name: Any,
    name: Any,
    *,
    fallback_name: str = "",
) -> str:
    module = normalize_string(module_name)
    reg_name = normalize_string(name, default=fallback_name)
    if not reg_name:
        return ""
    if module == "core" or not module or reg_name.startswith(f"{module}."):
        return reg_name
    return f"{module}.{reg_name}"


def os_key() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform == "win32":
        return "win32"
    return "other"
