import copy
from typing import Dict, Any, Optional, cast
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QLabel,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from ...base import BaseRenderer, emit_action
from .....state import Binding
from ....theme.tokens import theme_token

try:
    import pyqtgraph as pg

    PYQTGRAPH_AVAILABLE = True
except Exception:
    pg = None
    PYQTGRAPH_AVAILABLE = False


class ClickableFrame(QFrame):
    def __init__(
        self, action, item_data, surface_id, app_instance, comp_id, parent=None
    ):
        super().__init__(parent)
        self.action = action
        self.item_data = item_data
        self.surface_id = surface_id
        self.app_instance = app_instance
        self.comp_id = comp_id
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground)

        # Set active property if present in item_data
        is_active = item_data.get("active", False)
        self.setProperty("active", is_active)

    def mousePressEvent(self, event):
        if self.action:
            name = self.action.get("name")
            context = self.action.get("context", {})

            renderer = self.app_instance.renderer
            # state = getattr(self.app_instance, "state", {}) # Removed in refactoring
            resolved_context = renderer.resolve_bindings(context, item=self.item_data)

            emit_action(
                self.app_instance,
                name,
                resolved_context,
                self.surface_id,
                self.comp_id,
            )
        super().mousePressEvent(event)


class ChartRenderer(BaseRenderer):
    component_type = "Chart"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "chartType": self.PROPERTY,
            "chart_type": self.PROPERTY,
            "data": self.PROPERTY,
            "labels": self.PROPERTY,
            "title": self.PROPERTY,
            "max_height": self.PROPERTY,
            "max_width": self.PROPERTY,
        }

    def _draw_chart(self, widget, props: Dict[str, Any]) -> None:
        widget.clear()
        widget.showGrid(x=True, y=True, alpha=0.06)
        app_instance = widget.window()
        accent = theme_token("color.info", app_instance=app_instance) or "#0B4EA2"
        text_color = theme_token("data.text.primary", app_instance=app_instance) or "#FFFFFF"

        title = props.get("title", "")
        widget.setTitle(str(title) if title else "", color=text_color, size="10pt")

        data = props.get("data", [])
        labels = props.get("labels", [])
        chart_type = props.get("chartType", None) or props.get("chart_type", "bar")

        if not data:
            return

        x_vals = list(range(len(data)))
        if chart_type == "bar":
            bg = pg.BarGraphItem(
                x=x_vals,
                height=data,
                width=0.6,
                brush=accent,
                pen=pg.mkPen(color=accent, width=1),
            )
            widget.addItem(bg)
        elif chart_type == "line":
            pen = pg.mkPen(color=accent, width=1)
            widget.plot(
                x_vals,
                data,
                pen=pen,
                symbol="o",
                symbolSize=4,
                symbolBrush=accent,
            )
        elif chart_type == "area":
            curve = widget.plot(x_vals, data, pen=pg.mkPen(color=accent, width=2))
            fill_color = QColor(accent)
            fill_color.setAlpha(40)
            fill = pg.FillBetweenItem(
                pg.PlotDataItem(x_vals, [0] * len(data)),
                curve,
                brush=pg.mkBrush(fill_color),
            )
            widget.addItem(fill)

        if labels:
            ax = widget.getAxis("bottom")
            count = min(len(labels), len(x_vals))
            if count <= 6:
                label_indexes = list(range(count))
            else:
                step = max(1, (count - 1 + 4) // 5)
                label_indexes = list(range(0, count, step))
                if label_indexes[-1] != count - 1:
                    label_indexes.append(count - 1)
            ticks = [[(x_vals[index], str(labels[index])) for index in label_indexes]]
            ax.setTicks(ticks)
            ax.setPen(text_color, width=2)
            ax.setTextPen(text_color, width=2)

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        if not PYQTGRAPH_AVAILABLE:
            label = QLabel("Chart (Missing pyqtgraph)")
            label.setProperty("ui_role", "chart_missing")
            label.setMinimumHeight(250)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return label

        widget = pg.PlotWidget()
        widget.setObjectName(comp_id)
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        widget.setStyleSheet("background: transparent; border: none;")
        widget.setBackground(None)
        plot_item = widget.getPlotItem()
        plot_item.setMenuEnabled(False)
        plot_item.hideButtons()
        plot_item.vb.setMouseEnabled(x=False, y=False)
        plot_item.vb.setMenuEnabled(False)

        if props.get("max_width", None):
            widget.setMaximumWidth(props.get("max_width", 400))
        if props.get("max_height", None):
            widget.setMaximumHeight(int(props.get("max_height", 0)))

        widget._chart_props = dict(props)  # type: ignore[attr-defined]
        self._draw_chart(widget, widget._chart_props)  # type: ignore[attr-defined]

        widget.setMinimumHeight(250)

        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return widget

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if not PYQTGRAPH_AVAILABLE or not hasattr(widget, "_chart_props"):
            super().update_widget_property(widget, prop, value)
            return

        props = dict(getattr(widget, "_chart_props", {}) or {})
        if prop == "chart_type":
            props["chartType"] = value
        else:
            props[prop] = value

        if prop == "max_width":
            widget.setMaximumWidth(int(value or 16777215))
        elif prop == "max_height":
            widget.setMaximumHeight(int(value or 16777215))

        widget._chart_props = props  # type: ignore[attr-defined]
        if prop in {"chartType", "chart_type", "data", "labels", "title"}:
            self._draw_chart(widget, props)
            return

        super().update_widget_property(widget, prop, value)
