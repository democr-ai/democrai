from __future__ import annotations

from typing import Any, Dict, Optional

from democrai.sdk.components.base import Component


class Carousel(Component):
    """Template-driven carousel that renders one dataset item per slide."""
    type = "Carousel"

    def __init__(
        self,
        id: str,
        data_source: dict,
        item_template: Component,
        on_item_click: Optional[Dict[str, Any]] = None,
        on_change: Optional[Dict[str, Any]] = None,
        active_index: int = 0,
        autoplay: bool = False,
        interval_ms: int = 3000,
        show_dots: bool = True,
        show_arrows: bool = True,
        loop: bool = True,
    ):
        super().__init__(id)
        self.mutable_collection("dataSource").interactive()
        self.set_prop("dataSource", data_source)
        self.set_prop("itemTemplate", item_template.to_dict())
        self.set_prop("activeIndex", max(0, int(active_index)))
        self.set_prop("autoplay", bool(autoplay))
        self.set_prop("intervalMs", max(300, int(interval_ms)))
        self.set_prop("showDots", bool(show_dots))
        self.set_prop("showArrows", bool(show_arrows))
        self.set_prop("loop", bool(loop))
        if on_item_click:
            self.set_prop("onItemClick", on_item_click)
        if on_change:
            self.set_prop("onChange", on_change)

    def to_dict(self):
        """Serialize the carousel and mirror the template into the children contract."""
        data = super().to_dict()
        if "itemTemplate" in self.props:
            data["children"]["template"] = self.props["itemTemplate"]
        return data
