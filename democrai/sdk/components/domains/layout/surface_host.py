from typing import List, Optional, Any, Union
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class SurfaceHost(Container):
    """Host component that mounts another named surface inside the layout."""
    type = "SurfaceHost"

    def __init__(
        self,
        id: str,
        surface_id: str,
        children: Optional[List[Union[str, Component]]] = None,
    ):
        super().__init__(id, children)
        self.set_prop("surface_id", surface_id)
