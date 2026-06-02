from typing import Dict, Any, Optional, List
from democrai.sdk.components.base import Component


class List(Component):
    """Template-driven list component backed by an explicit data source."""
    type = "List"

    def __init__(
        self,
        id: str,
        data_source: dict,
        item_template: Optional[Component] = None,
        on_item_click: Optional[dict] = None,
        orientation: str = "vertical",
        selectable: bool = False,
        template: str = "custom",
        item_actions: Optional[List[Dict[str, Any]]] = None,
        selected_items_action: Optional[Dict[str, Any]] = None,
        selected_items_action_label: str = "Apply to selected",
    ):
        super().__init__(id)
        self.mutable_collection("dataSource").interactive()
        self.mutable_collection("itemActions").interactive()
        # dataSource: { type: 'inline'|'http'|'ws', url: '...', data: [...] }
        self.set_prop("dataSource", data_source)
        if item_template is not None:
            self.set_prop("itemTemplate", item_template.to_dict())
            self.set_prop("template", "custom")
        else:
            self.set_prop("template", template)
        self.set_prop("orientation", orientation)
        self.set_prop("selectable", selectable)
        self.set_prop("itemActions", item_actions if item_actions is not None else [])
        if selected_items_action:
            self.set_prop("selectedItemsAction", selected_items_action)
        if selected_items_action_label:
            self.set_prop("selectedItemsActionLabel", selected_items_action_label)
        if on_item_click:
            self.set_prop("onItemClick", on_item_click)

    def to_dict(self):
        """Serialize the list and mirror the template into the children contract."""
        data = super().to_dict()
        if "itemTemplate" in self.props:
            data["children"]["template"] = self.props["itemTemplate"]
        return data
