from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget
from ...base import BaseRenderer

class AccordionRenderer(BaseRenderer):
    component_type = "Accordion"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "items": self.COMPONENT,
            "multiple": self.COMPONENT,
            "collapsible": self.COMPONENT,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        del surface_id, app_instance
        container = QFrame()
        container.setObjectName(comp_id)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        container._accordion_items = props.get("items", []) if isinstance(props.get("items"), list) else []  # type: ignore[attr-defined]
        container._accordion_multiple = bool(props.get("multiple", False))  # type: ignore[attr-defined]
        container._accordion_collapsible = bool(props.get("collapsible", True))  # type: ignore[attr-defined]
        container._accordion_children = []  # type: ignore[attr-defined]
        self._rebuild(container)
        return container

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _rebuild(self, widget: QWidget) -> None:
        layout = widget.layout()
        if not isinstance(layout, QVBoxLayout):
            return
        children = getattr(widget, "_accordion_children", [])
        if isinstance(children, list):
            for child_widget in children:
                if isinstance(child_widget, QWidget):
                    child_widget.setParent(None)
        self._clear_layout(layout)

        items = getattr(widget, "_accordion_items", [])
        if not isinstance(items, list):
            items = []
        multiple = bool(getattr(widget, "_accordion_multiple", False))
        collapsible = bool(getattr(widget, "_accordion_collapsible", True))
        cards: list[tuple[QToolButton, QFrame]] = []
        panels: list[QFrame] = []

        def toggle_panel(index: int, checked: bool):
            if not checked and not multiple and not collapsible:
                cards[index][0].setChecked(True)
                return
            if checked and not multiple:
                for pos, (button, panel) in enumerate(cards):
                    if pos == index:
                        continue
                    button.setChecked(False)
                    panel.setVisible(False)
            cards[index][1].setVisible(checked)
            widget.updateGeometry()
            widget.adjustSize()

        for index, item in enumerate(items):
            block = QFrame()
            block.setProperty("ui_role", "accordion_block")
            block.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(14, 14, 14, 14)
            block_layout.setSpacing(10)

            button = QToolButton()
            button.setText(str(item.get("title") or item.get("label") or f"Item {index + 1}"))
            button.setCheckable(True)
            button.setChecked(bool(item.get("open", False)))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setArrowType(Qt.DownArrow if button.isChecked() else Qt.RightArrow)
            button.setProperty("ui_role", "accordion_trigger")
            panel = QFrame()
            panel.setVisible(button.isChecked())
            panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(6)

            content = QLabel(str(item.get("content", "")))
            content.setWordWrap(True)
            content.setProperty("ui_role", "accordion_content")
            content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
            panel_layout.addWidget(content)

            if item.get("meta"):
                meta = QLabel(str(item.get("meta")))
                meta.setProperty("ui_role", "accordion_meta")
                meta.setWordWrap(True)
                meta.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
                panel_layout.addWidget(meta)

            button.toggled.connect(lambda checked, idx=index, btn=button: btn.setArrowType(Qt.DownArrow if checked else Qt.RightArrow))
            button.toggled.connect(lambda checked, idx=index: toggle_panel(idx, checked))

            cards.append((button, panel))
            panels.append(panel)
            block_layout.addWidget(button)
            block_layout.addWidget(panel)
            layout.addWidget(block)

        setattr(widget, "_accordion_panels", panels)
        setattr(widget, "_accordion_child_index", 0)
        if isinstance(children, list):
            for child_widget in children:
                self._place_child(widget, child_widget)

    def add_child_to_widget(self, widget: QWidget, child_widget: QWidget) -> None:
        children = getattr(widget, "_accordion_children", None)
        if not isinstance(children, list):
            children = []
            setattr(widget, "_accordion_children", children)
        children.append(child_widget)
        self._place_child(widget, child_widget)

    def _place_child(self, widget: QWidget, child_widget: QWidget) -> None:
        panels = getattr(widget, "_accordion_panels", None)
        if isinstance(panels, list) and panels:
            index = int(getattr(widget, "_accordion_child_index", 0) or 0)
            if 0 <= index < len(panels):
                panel = panels[index]
                panel_layout = panel.layout()
                if panel_layout is not None:
                    panel_layout.addWidget(child_widget)
                    setattr(widget, "_accordion_child_index", index + 1)
                    return
        layout = widget.layout()
        if layout is not None:
            layout.addWidget(child_widget)

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "items":
            widget._accordion_items = value if isinstance(value, list) else []  # type: ignore[attr-defined]
            self._rebuild(widget)
            return
        if prop == "multiple":
            widget._accordion_multiple = bool(value)  # type: ignore[attr-defined]
            self._rebuild(widget)
            return
        if prop == "collapsible":
            widget._accordion_collapsible = bool(value)  # type: ignore[attr-defined]
            self._rebuild(widget)
            return
        super().update_widget_property(widget, prop, value)
