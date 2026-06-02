from __future__ import annotations

import re
from typing import Any

from democrai.sdk.ai_constants import normalize_capabilities


def sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return cleaned.strip("._") or "model"


def parse_capabilities(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\n,]+", str(value or ""))
    return normalize_capabilities(raw_items)
