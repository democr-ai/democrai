from __future__ import annotations
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QPoint, QRect, QSize
from PySide6.QtWidgets import QLayout, QStyle, QWidgetItem, QFrame, QWidget, QSizePolicy
from ...base import BaseRenderer


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing=10):
        super().__init__(parent)
        self._items: List[QWidgetItem] = []
        self.setSpacing(spacing)

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 10000), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            next_x = x + item.sizeHint().width() + spacing
            if next_x - spacing > rect.right() - margins.right() and line_height > 0:
                x = rect.x() + margins.left()
                y = y + line_height + spacing
                next_x = x + item.sizeHint().width() + spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + margins.bottom()


class FlowRenderer(BaseRenderer):
    component_type = "Flow"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children": self.COMPONENT,
            "spacing": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        spacing = int(props.get("spacing", 10) or 10)
        widget = QFrame()
        widget.setObjectName(comp_id)
        layout = FlowLayout(widget, spacing=spacing)
        widget.setLayout(layout)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if props.get("width", None):
            widget.setMaximumWidth(int(props.get("width") or 0))
        return widget

    def update_widget_property(self, widget, prop, value):
        if prop == "spacing":
            layout = widget.layout()
            if layout:
                layout.setSpacing(int(value or 10))
            return
        super().update_widget_property(widget, prop, value)
