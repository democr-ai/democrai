from typing import List, Optional, Any, Union
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class Grid(Container):
    """A grid layout component."""

    type = "Grid"

    def __init__(
        self,
        id: str,
        children: Optional[List[Union[str, Component]]] = None,
        columns: int = 2,
    ):
        super().__init__(id, children)
        self.set_prop("columns", columns)
