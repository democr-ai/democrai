from typing import List, Optional, Any, Union
from democrai.sdk.components.base import Component

class Container(Component):
    """Base for components that have children."""

    def __init__(self, id: str, children: Optional[List[Union[str, Component]]] = None):
        super().__init__(id)
        if children:
            self.set_children(children)

    def set_children(self, children: List[Union[str, Component]]):
        """Replace the explicit child list of the container."""
        self.children = children
        return self
