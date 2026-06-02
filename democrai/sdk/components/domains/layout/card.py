from typing import List, Optional, Any, Union, Dict
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class Card(Container):
    """A card container for displaying related information.

    Supports optional item_actions (a list of action defs) that render as a
    3-dot dropdown menu in the card corner. Each action dict format:
        {"label": "Edit", "icon": "ric.edit-line", "action": {"name": "my.action", "context": {...}}}

    The optional data dict is merged into the action context when triggered.
    """

    type = "Card"

    def __init__(
        self,
        id: str,
        children: Optional[List[Union[str, Component]]] = None,
        background_image: Optional[str] = None,
        variant: str = "elevated",
        item_actions: Optional[List[Dict[str, Any]]] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(id, children)
        self.set_prop("variant", variant)
        if background_image:
            self.set_prop("background_image", background_image)
        if item_actions:
            self.set_prop("itemActions", item_actions)
        if data:
            self.set_prop("data", data)
