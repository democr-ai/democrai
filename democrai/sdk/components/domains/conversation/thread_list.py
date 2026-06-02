from __future__ import annotations
from typing import Any, Dict, List, Optional
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class ThreadList(Component):
    """List of conversation threads with optional active-thread tracking."""
    type = "ThreadList"

    def __init__(self, id: str, threads: Optional[List[Dict[str, Any]]] = None, active_thread_id: str = "", action: Optional[Any] = None, params: Optional[dict] = None):
        super().__init__(id)
        self.mutable_collection("threads").allow("active_thread_id.set").interactive()
        self.set_prop("threads", threads if threads is not None else [])
        self.set_prop("active_thread_id", active_thread_id)
        if action:
            if isinstance(action, dict):
                self.set_prop("action", action)
            else:
                self.set_action(str(action), params)
