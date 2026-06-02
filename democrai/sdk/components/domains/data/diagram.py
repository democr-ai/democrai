from __future__ import annotations

from typing import Any, Optional

from democrai.sdk.components.base import Component


class Diagram(Component):
    """Node-and-edge diagram component."""
    type = "Diagram"

    def __init__(
        self,
        id: str,
        *,
        nodes: Optional[list[dict[str, Any]]] = None,
        edges: Optional[list[dict[str, Any]]] = None,
        mermaid: str = "",
        direction: str = "LR",
        title: str = "",
        height: int = 360,
        node_width: int = 180,
        node_height: int = 72,
    ):
        super().__init__(id)
        self.set_prop("nodes", nodes if nodes is not None else [])
        self.set_prop("edges", edges if edges is not None else [])
        self.set_prop("direction", direction.upper())
        self.set_prop("height", max(180, int(height)))
        self.set_prop("nodeWidth", max(96, int(node_width)))
        self.set_prop("nodeHeight", max(48, int(node_height)))
        if mermaid:
            self.set_prop("mermaid", mermaid)
        if title:
            self.set_prop("title", title)
