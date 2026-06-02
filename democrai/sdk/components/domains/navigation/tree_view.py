from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component


class TreeView(Component):
    """Tree-view component for nested hierarchical node structures."""
    type = "TreeView"

    def __init__(
        self,
        id: str,
        nodes: Optional[List[Dict[str, Any]]] = None,
        *,
        click_action: Optional[str] = None,
        select_action: Optional[str] = None,
        params: Optional[dict] = None,
        expand_all: bool = False,
        click_mode: str = "single",
        selection_mode: str = "single",
        active_id: Optional[str] = None,
    ):
        super().__init__(id)
        self.set_prop("nodes", nodes if nodes is not None else [])
        self.set_prop("click_action", click_action if click_action is not None else "")
        self.set_prop("select_action", select_action if select_action is not None else "")
        self.set_prop("params", params if params is not None else {})
        self.set_prop("expand_all", expand_all)
        self.set_prop("click_mode", click_mode)
        self.set_prop("selection_mode", selection_mode)
        self.set_prop("active_id", active_id)
