from typing import List, Optional, Any, Union
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class Tabs(Container):
    """Tabbed container supporting inline and route-backed tab content."""
    type = "Tabs"

    def __init__(self, id: str, children: Optional[List[Union[str, Component]]] = None):
        super().__init__(id, children)
        self.set_prop("tabs", [])

    def add_tab(
        self,
        child_id: str,
        label: str,
        *,
        route: Optional[str] = None,
        icon: Optional[str] = None,
    ):
        """Register a tab.

        Args:
            child_id: ID of the child component to show inside this tab (ignored when route is set).
            label:    Tab label text.
            route:    Optional route path. When provided the tab navigates to this path instead of
                      rendering inline content.
            icon:     Optional remix-icon name (e.g. ``"ric.settings-line"``).
        """
        tabs = self.props.get("tabs", [])
        entry: dict = {"id": child_id, "label": label}
        if route:
            entry["route"] = route
        if icon:
            entry["icon"] = icon
        tabs.append(entry)
        self.set_prop("tabs", tabs)
        return self
