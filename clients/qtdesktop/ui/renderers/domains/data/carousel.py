from __future__ import annotations

import copy
from typing import Any, Dict, cast

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from ...icon import get_icon, get_icon_gliph
from .....state import Binding
from ...base import BaseRenderer, emit_action_spec
from ...collection_patch import patch_collection


class _ClickableSlide(QFrame):
    def __init__(
        self,
        action: dict[str, Any] | None,
        item_data: dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str,
        parent=None,
    ):
        super().__init__(parent)
        self._action = action or {}
        self._item_data = dict(item_data or {})
        self._surface_id = surface_id
        self._app_instance = app_instance
        self._comp_id = comp_id
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground)

    def mousePressEvent(self, event):
        name = str(self._action.get("name") or "").strip()
        if name:
            context = self._action.get("context", {})
            resolved_context = self._app_instance.renderer.resolve_bindings(
                context,
                item=self._item_data,
            )
            emit_action_spec(
                self._app_instance,
                self._action,
                resolved_context,
                self._surface_id,
                self._comp_id,
            )
        super().mousePressEvent(event)


class CarouselRenderer(BaseRenderer):
    component_type = "Carousel"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "dataSource": self.PROPERTY,
            "itemTemplate": self.COMPONENT,
            "onItemClick": self.COMPONENT,
            "onChange": self.COMPONENT,
            "activeIndex": self.PROPERTY,
            "autoplay": self.PROPERTY,
            "intervalMs": self.PROPERTY,
            "showDots": self.COMPONENT,
            "showArrows": self.COMPONENT,
            "loop": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        root = QFrame()
        root.setObjectName(comp_id)
        root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        root.setProperty("type", "card")
        root.setProperty("variant", props.get("variant", "outlined"))
        root.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        stack = QStackedWidget()
        stack.setObjectName(f"{comp_id}_stack")
        stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(stack)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 4, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        prev_btn = QPushButton()
        prev_btn.setIcon(get_icon("ric.arrow-left-long-fill"))
        prev_btn.setObjectName(f"{comp_id}_prev")
        prev_btn.setFixedSize(32, 32)
        prev_btn.setCursor(Qt.PointingHandCursor)
        prev_btn.setProperty("variant", "primary")
        prev_btn.setProperty("mode", "ghost")
        # prev_btn.setProperty("appearance", "outline")
        prev_btn.style().unpolish(prev_btn)
        prev_btn.style().polish(prev_btn)
        controls_layout.addWidget(prev_btn)

        dots_host = QWidget()
        dots_layout = QHBoxLayout(dots_host)
        dots_layout.setContentsMargins(0, 0, 0, 0)
        dots_layout.setSpacing(6)
        controls_layout.addWidget(dots_host)

        next_btn = QPushButton()
        next_btn.setIcon(get_icon("ric.arrow-right-long-fill"))
        next_btn.setObjectName(f"{comp_id}_next")
        next_btn.setFixedSize(32, 32)
        next_btn.setCursor(Qt.PointingHandCursor)
        next_btn.setProperty("variant", "primary")
        next_btn.setProperty("mode", "ghost")
        # next_btn.setProperty("appearance", "outline")
        next_btn.style().unpolish(next_btn)
        next_btn.style().polish(next_btn)
        controls_layout.addWidget(next_btn)
        layout.addWidget(controls)

        root.props = props  # type: ignore[attr-defined]
        root.surface_id = surface_id  # type: ignore[attr-defined]
        root.app_instance = app_instance  # type: ignore[attr-defined]
        root.comp_id = comp_id  # type: ignore[attr-defined]
        root._carousel_stack = stack  # type: ignore[attr-defined]
        root._carousel_controls = controls  # type: ignore[attr-defined]
        root._carousel_prev_btn = prev_btn  # type: ignore[attr-defined]
        root._carousel_next_btn = next_btn  # type: ignore[attr-defined]
        root._carousel_dots_host = dots_host  # type: ignore[attr-defined]
        root._carousel_dots_layout = dots_layout  # type: ignore[attr-defined]
        root._carousel_dots = []  # type: ignore[attr-defined]
        root._carousel_data_items = []  # type: ignore[attr-defined]
        root._carousel_index = max(0, int(props.get("activeIndex", 0) or 0))  # type: ignore[attr-defined]
        root._carousel_timer = QTimer(root)  # type: ignore[attr-defined]
        root._carousel_timer.timeout.connect(lambda: self._advance(root, +1, emit_change=True))  # type: ignore[attr-defined]

        prev_btn.clicked.connect(lambda: self._advance(root, -1, emit_change=True))
        next_btn.clicked.connect(lambda: self._advance(root, +1, emit_change=True))

        data_source = props.get("dataSource", {})
        ds_type = str(data_source.get("type", "inline")).strip().lower()
        if ds_type == "inline":
            self._populate_carousel(root, list(data_source.get("data", [])))
        elif ds_type == "binding":
            data = data_source.get("data", {})
            if isinstance(data, dict) and data.get("type") == "store":
                path = data.get("path")
                if path:
                    key = (
                        path
                        if isinstance(path, str) and path.startswith("/")
                        else f"/{str(path).lstrip('/')}"
                    )

                    def set_carousel(v):
                        self._populate_carousel(root, v if isinstance(v, list) else [])

                    app_instance.binder.bind(
                        Binding(
                            key=key,
                            widget=root,
                            set_widget=set_carousel,
                            transform_from_store=lambda v: v or [],
                        )
                    )
            elif isinstance(data, dict) and isinstance(data.get("path"), str):
                surface_data = app_instance.bindings.read_surface_data(
                    surface_id,
                    data.get("path"),
                    data.get("default", []),
                )
                self._populate_carousel(
                    root,
                    surface_data if isinstance(surface_data, list) else [],
                )
            elif isinstance(data, list):
                self._populate_carousel(root, data)
        else:
            self._populate_carousel(root, [])

        self._apply_controls_visibility(root)
        self._configure_autoplay(root)
        return root

    def apply_collection_patch(
        self,
        widget: QWidget,
        prop: str,
        action: str,
        value: Any,
    ) -> bool:
        if prop not in {"dataSource", "dataSource.data"}:
            return False
        data_items = list(getattr(widget, "_carousel_data_items", []))
        payload = value
        if action == "set" and prop == "dataSource" and isinstance(value, dict):
            payload = value.get("data", [])
        patch = patch_collection(data_items, action, payload)
        if not patch.handled:
            return False
        self._populate_carousel(widget, patch.items)
        return True

    def update_widget_property(self, widget: QWidget, prop: str, value: Any):
        if prop in {"dataSource", "dataSource.data"}:
            data_items = value if prop == "dataSource.data" else value.get("data", [])
            if isinstance(data_items, list):
                self._populate_carousel(widget, data_items)
            return
        if prop == "activeIndex":
            self._set_active_index(widget, int(value or 0), emit_change=False)
            return
        if prop == "autoplay":
            widget.props["autoplay"] = bool(value)  # type: ignore[attr-defined]
            self._configure_autoplay(widget)
            return
        if prop == "intervalMs":
            widget.props["intervalMs"] = max(300, int(value or 3000))  # type: ignore[attr-defined]
            self._configure_autoplay(widget)
            return
        if prop == "loop":
            widget.props["loop"] = bool(value)  # type: ignore[attr-defined]
            self._configure_autoplay(widget)
            return
        super().update_widget_property(widget, prop, value)

    def _make_ids_unique(self, comp_def: dict, suffix: str):
        if "id" in comp_def:
            comp_def["id"] = f"{comp_def['id']}_{suffix}"

        c_type = list(comp_def["component"].keys())[0]
        comp_props = comp_def["component"][c_type]
        children_node = comp_def.get("children") or comp_props.get("children", {})
        if isinstance(children_node, dict) and "explicitList" in children_node:
            for child in children_node["explicitList"]:
                if isinstance(child, dict):
                    self._make_ids_unique(child, suffix)

    def _populate_carousel(self, container: QWidget, data_items: list[dict[str, Any]]):
        container._carousel_data_items = list(data_items or [])  # type: ignore[attr-defined]
        stack = cast(QStackedWidget, container._carousel_stack)  # type: ignore[attr-defined]
        while stack.count():
            widget = stack.widget(0)
            stack.removeWidget(widget)
            widget.deleteLater()

        template = container.props.get("itemTemplate")  # type: ignore[attr-defined]
        on_click = container.props.get("onItemClick")  # type: ignore[attr-defined]
        if not isinstance(template, dict):
            self._rebuild_dots(container, 0)
            self._apply_controls_visibility(container)
            return

        for index, item_data in enumerate(data_items):
            if not isinstance(item_data, dict):
                continue
            item_template = copy.deepcopy(template)
            self._make_ids_unique(item_template, str(index))
            item_widget = container.app_instance.renderer.build_widget(  # type: ignore[attr-defined]
                container.surface_id,  # type: ignore[attr-defined]
                container.app_instance.surfaces,  # type: ignore[attr-defined]
                comp_def=item_template,
                item=item_data,
                app_instance=container.app_instance,  # type: ignore[attr-defined]
            )
            if not item_widget:
                continue

            if on_click:
                wrapper = _ClickableSlide(
                    on_click,
                    item_data,
                    container.surface_id,  # type: ignore[attr-defined]
                    container.app_instance,  # type: ignore[attr-defined]
                    container.comp_id,  # type: ignore[attr-defined]
                )
                wrapper_layout = QVBoxLayout(wrapper)
                wrapper_layout.setContentsMargins(0, 0, 0, 0)
                wrapper_layout.addWidget(item_widget)
                stack.addWidget(wrapper)
            else:
                stack.addWidget(item_widget)

        self._rebuild_dots(container, stack.count())
        current = min(int(container._carousel_index), max(0, stack.count() - 1))  # type: ignore[attr-defined]
        self._set_active_index(container, current, emit_change=False)
        self._apply_controls_visibility(container)
        self._configure_autoplay(container)

    def _rebuild_dots(self, container: QWidget, count: int):
        dots_layout = cast(QHBoxLayout, container._carousel_dots_layout)  # type: ignore[attr-defined]
        while dots_layout.count():
            item = dots_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        dots: list[QPushButton] = []
        for i in range(count):
            dot = QPushButton()
            dot.setText(str(i + 1))
            dot.setCursor(Qt.PointingHandCursor)
            dot.setProperty("variant", "default")
            dot.setProperty("mode", "ghost")
            dot.clicked.connect(
                lambda _checked=False, idx=i: self._set_active_index(
                    container, idx, emit_change=True
                )
            )
            dots_layout.addWidget(dot)
            dots.append(dot)
        container._carousel_dots = dots  # type: ignore[attr-defined]

    def _set_active_index(self, container: QWidget, index: int, *, emit_change: bool):
        stack = cast(QStackedWidget, container._carousel_stack)  # type: ignore[attr-defined]
        total = stack.count()
        if total <= 0:
            container._carousel_index = 0  # type: ignore[attr-defined]
            return
        loop = bool(container.props.get("loop", True))  # type: ignore[attr-defined]
        if loop:
            normalized = index % total
        else:
            normalized = max(0, min(index, total - 1))

        container._carousel_index = normalized  # type: ignore[attr-defined]
        stack.setCurrentIndex(normalized)
        for dot_index, dot in enumerate(list(container._carousel_dots)):  # type: ignore[attr-defined]
            is_active = dot_index == normalized
            dot.setProperty("active", "true" if is_active else "false")
            dot.setProperty("mode", "solid" if is_active else "ghost")
            dot.style().unpolish(dot)
            dot.style().polish(dot)

        if emit_change:
            self._emit_change(container)

    def _advance(self, container: QWidget, delta: int, *, emit_change: bool):
        current = int(getattr(container, "_carousel_index", 0))
        self._set_active_index(container, current + delta, emit_change=emit_change)

    def _emit_change(self, container: QWidget):
        on_change = container.props.get("onChange")  # type: ignore[attr-defined]
        name = str((on_change or {}).get("name") or "").strip()
        if not name:
            return
        context = dict((on_change or {}).get("context") or {})
        index = int(getattr(container, "_carousel_index", 0))
        data_items = list(getattr(container, "_carousel_data_items", []))
        item = (
            data_items[index]
            if 0 <= index < len(data_items) and isinstance(data_items[index], dict)
            else {}
        )
        resolved = container.app_instance.renderer.resolve_bindings(context, item=item)  # type: ignore[attr-defined]
        payload = {
            **(resolved if isinstance(resolved, dict) else {}),
            "source": "carousel",
            "index": index,
            "itemId": item.get("id"),
        }
        emit_action_spec(
            container.app_instance,  # type: ignore[attr-defined]
            on_change,
            payload,
            container.surface_id,  # type: ignore[attr-defined]
            container.comp_id,  # type: ignore[attr-defined]
        )

    def _apply_controls_visibility(self, container: QWidget):
        show_arrows = bool(container.props.get("showArrows", True))  # type: ignore[attr-defined]
        show_dots = bool(container.props.get("showDots", True))  # type: ignore[attr-defined]
        stack = cast(QStackedWidget, container._carousel_stack)  # type: ignore[attr-defined]
        has_many = stack.count() > 1
        container._carousel_prev_btn.setVisible(show_arrows and has_many)  # type: ignore[attr-defined]
        container._carousel_next_btn.setVisible(show_arrows and has_many)  # type: ignore[attr-defined]
        container._carousel_dots_host.setVisible(show_dots and has_many)  # type: ignore[attr-defined]
        container._carousel_controls.setVisible(has_many)  # type: ignore[attr-defined]

    def _configure_autoplay(self, container: QWidget):
        timer = cast(QTimer, container._carousel_timer)  # type: ignore[attr-defined]
        stack = cast(QStackedWidget, container._carousel_stack)  # type: ignore[attr-defined]
        autoplay = bool(container.props.get("autoplay", False))  # type: ignore[attr-defined]
        interval_ms = max(300, int(container.props.get("intervalMs", 3000) or 3000))  # type: ignore[attr-defined]
        if autoplay and stack.count() > 1:
            timer.start(interval_ms)
        else:
            timer.stop()
