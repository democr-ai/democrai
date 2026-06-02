from __future__ import annotations

from typing import Any, Optional

from democrai.sdk.components.base import Component


def _is_binding(value: Any) -> bool:
    return isinstance(value, dict) and (
        value.get("type") in {"store", "data", "action", "literal"}
        or ("path" in value and len(value.keys()) <= 3)
    )


class GitGraph(Component):
    """Git history visualization component."""
    type = "GitGraph"

    def __init__(
        self,
        id: str,
        *,
        commits: Optional[list[dict[str, Any]]] = None,
        edges: Optional[list[dict[str, Any]]] = None,
        title: str = "",
        height: int = 360,
        lane_width: int = 80,
        row_height: int = 56,
        show_labels: bool = True,
        show_branch_names: bool = True,
        action: Any = "",
        params: Optional[dict[str, Any]] = None,
    ):
        super().__init__(id)
        self.set_prop("commits", commits if commits is not None else [])
        self.set_prop("edges", edges if edges is not None else [])
        self.set_prop("height", max(220, int(height)))
        self.set_prop("laneWidth", max(48, int(lane_width)))
        self.set_prop("rowHeight", max(34, int(row_height)))
        self.set_prop("showLabels", show_labels)
        self.set_prop("showBranchNames", show_branch_names)
        if action:
            self.set_prop("action", action)
        if params:
            self.set_prop("params", params)
        if title:
            self.set_prop("title", title)
