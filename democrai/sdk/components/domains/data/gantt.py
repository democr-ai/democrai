from __future__ import annotations

from typing import Any, Optional

from democrai.sdk.components.base import Component


def _is_binding(value: Any) -> bool:
    return isinstance(value, dict) and (
        value.get("type") in {"store", "data", "action", "literal"}
        or ("path" in value and len(value.keys()) <= 3)
    )


class Gantt(Component):
    """Gantt timeline component for scheduled items."""
    type = "Gantt"

    def __init__(
        self,
        id: str,
        *,
        items: Optional[list[dict[str, Any]]] = None,
        mermaid: str = "",
        title: str = "",
        height: int = 360,
        start: str = "",
        end: str = "",
        scale: str = "1d",
    ):
        super().__init__(id)
        self.set_prop("items", items if items is not None else [])
        self.set_prop("height", max(220, int(height)))
        if scale:
            self.set_prop("scale", scale)
        if mermaid:
            self.set_prop("mermaid", mermaid)
        if title:
            self.set_prop("title", title)
        if start:
            self.set_prop("start", start)
        if end:
            self.set_prop("end", end)
