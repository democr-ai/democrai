from __future__ import annotations

from typing import Any, Optional

from democrai.sdk.components.base import Component


def _is_binding(value: Any) -> bool:
    return isinstance(value, dict) and (
        value.get("type") in {"store", "data", "action", "literal"}
        or ("path" in value and len(value.keys()) <= 3)
    )


class SequenceDiagram(Component):
    """Sequence diagram component for participants and exchanged messages."""
    type = "SequenceDiagram"

    def __init__(
        self,
        id: str,
        *,
        participants: Optional[list[dict[str, Any]]] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        mermaid: str = "",
        title: str = "",
        height: int = 360,
    ):
        super().__init__(id)
        self.set_prop(
            "participants",
            participants if participants is not None else [],
        )
        self.set_prop("messages", messages if messages is not None else [])
        self.set_prop("height", max(220, int(height)))
        if mermaid:
            self.set_prop("mermaid", mermaid)
        if title:
            self.set_prop("title", title)
