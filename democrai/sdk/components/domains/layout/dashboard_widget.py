from typing import List, Optional, Any, Union
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class DashboardWidget(Container):
    """A draggable widget for the dashboard."""

    type = "DashboardWidget"

    def __init__(
        self,
        id: str,
        size: str = "square",
        title: str = "",
        children: Optional[List[Union[str, Component]]] = None,
    ):
        super().__init__(id, children)
        self.set_prop("size", size)  # square, rect_h, rect_v
        self.set_prop("title", title)
