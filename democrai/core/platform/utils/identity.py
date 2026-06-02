from __future__ import annotations

from typing import Any


def to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except Exception:
        return None


def to_required_int(value: Any, field_name: str) -> int:
    normalized = to_optional_int(value)
    if normalized is None:
        raise ValueError(f"{field_name} must be an integer")
    return normalized


def to_int_or_zero(value: Any) -> int:
    normalized = to_optional_int(value)
    return normalized if normalized is not None else 0


def normalize_organization_id(value: Any) -> int:
    return to_int_or_zero(value)


def denormalize_organization_id(value: Any) -> int | None:
    normalized = to_optional_int(value)
    if normalized in (None, 0):
        return None
    return normalized
