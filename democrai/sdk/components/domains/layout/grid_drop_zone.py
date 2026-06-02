from typing import List, Optional, Any, Union
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class GridDropZone(Container):
    """A grid where widgets can be dropped."""

    type = "GridDropZone"

    def __init__(
        self,
        id: str,
        columns: int = 4,
        rows: int = 4,
        insertable_items: Optional[List[dict]] = None,
        children: Optional[List[Union[str, Component]]] = None,
    ):
        super().__init__(id, children)
        self.set_prop("columns", columns)
        self.set_prop("rows", rows)
        if insertable_items is not None:
            self.set_prop("insertable_items", insertable_items)
