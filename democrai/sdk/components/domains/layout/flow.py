from typing import List, Optional, Any, Union
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class Flow(Container):
    """A layout component that wraps its children horizontally."""

    type = "Flow"

    def __init__(
        self,
        id: str,
        children: Optional[List[Union[str, Component]]] = None,
        spacing: int = 10,
    ):
        super().__init__(id, children)
        self.set_prop("spacing", spacing)
