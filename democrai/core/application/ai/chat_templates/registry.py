from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


_CHAT_TEMPLATES: dict[str, dict[str, Any]] = {
    "gemma4_thinking": {
        "name": "gemma4_thinking",
        "path": "templates/gemma4_thinking.jinja",
    },
    "qwen35_vl_thinking": {
        "name": "qwen35_vl_thinking",
        "path": "templates/qwen35_vl_thinking.jinja",
    },
}


def list_chat_templates() -> list[str]:
    return list(_CHAT_TEMPLATES.keys())


def get_chat_template(name: str | None = None) -> dict[str, Any] | None:
    if not name:
        return None
    template = _CHAT_TEMPLATES.get(name.lower())
    if template is None:
        raise ValueError(f"unsupported_chat_template:{name}")
    resolved = deepcopy(template)
    path = Path(__file__).parent / str(resolved.pop("path"))
    resolved["template"] = path.read_text(encoding="utf-8")
    return resolved
