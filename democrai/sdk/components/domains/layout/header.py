from typing import List, Optional, Union
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class Header(Container):
    """Three-slot header container with left, center, and right regions."""
    type = "Header"

    def __init__(
        self,
        id: str,
        children: Optional[List[Union[str, Component]]] = None,
        *,
        left: Optional[List[Union[str, Component]]] = None,
        center: Optional[List[Union[str, Component]]] = None,
        right: Optional[List[Union[str, Component]]] = None,
    ):
        super().__init__(id, children)
        self.set_prop("left", left if left is not None else [])
        self.set_prop("center", center if center is not None else [])
        self.set_prop("right", right if right is not None else [])

    def set_left(self, children: List[Union[str, Component]]):
        """Replace the content rendered in the left slot."""
        self.set_prop("left", children)
        return self

    def set_center(self, children: List[Union[str, Component]]):
        """Replace the content rendered in the center slot."""
        self.set_prop("center", children)
        return self

    def set_right(self, children: List[Union[str, Component]]):
        """Replace the content rendered in the right slot."""
        self.set_prop("right", children)
        return self
