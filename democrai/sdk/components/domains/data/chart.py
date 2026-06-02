from typing import List, Optional, Any
from democrai.sdk.components.base import Component


class Chart(Component):
    """A chart component for data visualization."""

    type = "Chart"

    def __init__(
        self,
        id: str,
        chart_type: str = "Line",
        data: Optional[List[Any]] = None,
        labels: Optional[List[str]] = None,
        title: Optional[str] = None,
    ):
        super().__init__(id)
        self.set_prop("chartType", chart_type)
        if data:
            self.set_prop("data", data)
        if labels:
            self.set_prop("labels", labels)
        if title:
            self.set_prop("title", title)
