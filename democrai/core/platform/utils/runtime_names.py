from __future__ import annotations

import re
from typing import Any


RUNTIME_NAME_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
RUNTIME_ASSET_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
QUALIFIED_RUNTIME_NAME_PATTERN = re.compile(
    r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*$"
)
RUNTIME_NAME_PATTERN_DESCRIPTION = (
    "segments may contain only ASCII letters, digits, and hyphens; dots are "
    "reserved as namespace separators"
)


def is_valid_runtime_name_segment(value: Any) -> bool:
    normalized = value.strip() if isinstance(value, str) else ""
    return bool(normalized and RUNTIME_NAME_SEGMENT_PATTERN.fullmatch(normalized))


def validate_runtime_name_segment(value: Any, *, kind: str = "name") -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not is_valid_runtime_name_segment(normalized):
        raise ValueError(f"{kind} is invalid: {RUNTIME_NAME_PATTERN_DESCRIPTION}")
    return normalized


def is_valid_runtime_asset_owner(value: Any) -> bool:
    normalized = value.strip() if isinstance(value, str) else ""
    return bool(normalized and RUNTIME_ASSET_OWNER_PATTERN.fullmatch(normalized))


def is_valid_qualified_runtime_name(value: Any) -> bool:
    normalized = value.strip() if isinstance(value, str) else ""
    return bool(normalized and QUALIFIED_RUNTIME_NAME_PATTERN.fullmatch(normalized))


def validate_qualified_runtime_name(value: Any, *, kind: str = "runtime name") -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not is_valid_qualified_runtime_name(normalized):
        raise ValueError(f"{kind} is invalid: {RUNTIME_NAME_PATTERN_DESCRIPTION}")
    return normalized
