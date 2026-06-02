import copy
from typing import Dict, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QPushButton,
    QToolButton,
    QSizePolicy,
    QMenu,
    QAbstractButton,
)

from ...base import BaseRenderer, emit_action_spec
from ...base_visibility import spec_is_visible
from ...collection_patch import patch_collection
from ...icon import get_icon, normalize_icon_name
from ....theme.tokens import theme_token
from .....state import Binding


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _is_checked_state(state: Any) -> bool:
    if state == Qt.CheckState.Checked:
        return True
    if state == Qt.CheckState.Unchecked:
        return False
    raw = getattr(state, "value", state)
    return raw == 2


class ListItemFrame(QFrame):
    def __init__(self, on_primary_click=None, parent=None):
        super().__init__(parent)
        self._on_primary_click = on_primary_click

    def mousePressEvent(self, event):  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton and self._on_primary_click:
            target = self.childAt(event.position().toPoint())
            if isinstance(target, QAbstractButton):
                super().mousePressEvent(event)
                return
            self._on_primary_click()
        super().mousePressEvent(event)


class ListRenderer(BaseRenderer):
    component_type = "List"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "dataSource": self.PROPERTY,
            "itemTemplate": self.COMPONENT,
            "onItemClick": self.COMPONENT,
            "orientation": self.COMPONENT,
            "selectable": self.PROPERTY,
            "template": self.COMPONENT,
            "itemActions": self.PROPERTY,
            "selectedItemsAction": self.PROPERTY,
            "selectedItemsActionLabel": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        container = QFrame()
        container.setObjectName(comp_id)

        orientation = props.get("orientation", "vertical")
        if orientation == "horizontal":
            layout: Any = QHBoxLayout(container)
        else:
            layout = QVBoxLayout(container)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        container.props = props  # type: ignore[attr-defined]
        container.surface_id = surface_id  # type: ignore[attr-defined]
        container.app_instance = app_instance  # type: ignore[attr-defined]
        container.comp_id = comp_id  # type: ignore[attr-defined]
        container._list_data_items = []  # type: ignore[attr-defined]
        container._selected_item_keys = set()  # type: ignore[attr-defined]
        container._selected_action_button = None  # type: ignore[attr-defined]

        data_source = props.get("dataSource", {})
        if not isinstance(data_source, dict):
            data_source = {}
        ds_type = data_source.get("type", "inline")

        if ds_type == "inline":
            self._populate_list(container, data_source.get("data", []))
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

                    def set_list(v):
                        self._populate_list(container, v if isinstance(v, list) else [])

                    app_instance.binder.bind(
                        Binding(
                            key=key,
                            widget=container,
                            set_widget=set_list,
                            transform_from_store=lambda v: v or [],
                        )
                    )
            elif isinstance(data, dict) and isinstance(data.get("path"), str):
                surface_data = app_instance.bindings.read_surface_data(
                    surface_id,
                    data.get("path"),
                    data.get("default", []),
                )
                self._populate_list(
                    container,
                    surface_data if isinstance(surface_data, list) else [],
                )
            elif isinstance(data, list):
                self._populate_list(container, data)

        container.setProperty("type", "list")
        return container

    def apply_collection_patch(
        self,
        widget: QWidget,
        prop: str,
        action: str,
        value: Any,
    ) -> bool:
        if prop not in {"dataSource", "dataSource.data"}:
            return False

        data_items = list(getattr(widget, "_list_data_items", []))
        payload = value
        if action == "set" and prop == "dataSource" and isinstance(value, dict):
            payload = value.get("data", [])

        patch = patch_collection(data_items, action, payload)
        if not patch.handled:
            return False

        self._populate_list(widget, patch.items)
        return True

    def update_widget_property(self, widget: QWidget, prop: str, value: Any):
        if prop == "dataSource.data" or prop == "dataSource":
            data_items = value if prop == "dataSource.data" else value.get("data", [])
            if isinstance(data_items, list):
                self._populate_list(widget, data_items)
            return

        if prop in {
            "itemActions",
            "selectedItemsAction",
            "selectedItemsActionLabel",
            "itemTemplate",
            "template",
            "onItemClick",
            "selectable",
        }:
            widget.props[prop] = value  # type: ignore[attr-defined]
            data_items = list(getattr(widget, "_list_data_items", []))
            self._populate_list(widget, data_items)
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

    def _item_key(self, item_data: dict, index: int) -> str:
        item_id = item_data.get("id")
        if item_id is None or item_id == "":
            return f"idx:{index}"
        return f"id:{item_id}"

    def _selected_items(self, container: QFrame) -> list[dict]:
        selected_keys = set(getattr(container, "_selected_item_keys", set()))
        selected: list[dict] = []
        for index, raw in enumerate(getattr(container, "_list_data_items", [])):
            if not isinstance(raw, dict):
                continue
            if self._item_key(raw, index) in selected_keys:
                selected.append(dict(raw))
        return selected

    def _emit_action(
        self,
        container: QFrame,
        action_spec: Any,
        item: dict | None = None,
        extra: dict | None = None,
    ):
        if isinstance(action_spec, dict):
            context = (
                action_spec.get("context", {})
                if isinstance(action_spec.get("context"), dict)
                else {}
            )
            dispatch_spec = dict(action_spec)
            dispatch_spec["context"] = {}
        elif isinstance(action_spec, str):
            context = {}
            dispatch_spec = action_spec
        else:
            return

        resolved_item = item if isinstance(item, dict) else {}
        resolved_context = container.app_instance.renderer.resolve_bindings(
            context, item=resolved_item
        )
        if isinstance(extra, dict):
            resolved_context.update(extra)

        emit_action_spec(
            container.app_instance,
            dispatch_spec,
            resolved_context,
            container.surface_id,
            container.comp_id,
        )

    def _build_default_item_widget(self, item_ctx: dict, template_name: str) -> QWidget:
        base = QFrame()
        base.setProperty("type", "list_item_content")
        row = QHBoxLayout(base)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        icon_name = str(item_ctx.get("icon") or "").strip()
        if icon_name:
            icon_label = QLabel()
            icon_color = (
                str(item_ctx.get("icon_color") or "#94A3B8").strip() or "#94A3B8"
            )
            icon = get_icon(normalize_icon_name(icon_name), icon_color, 16)
            icon_label.setPixmap(icon.pixmap(16, 16))
            row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        if template_name == "title_text":
            title = QLabel(str(item_ctx.get("title") or ""))
            title.setProperty("ui_role", "list_item_title")
            text_col.addWidget(title)
            raw_badges = item_ctx.get("badges")
            if isinstance(raw_badges, list) and raw_badges:
                badges_row = QHBoxLayout()
                badges_row.setContentsMargins(0, 0, 0, 0)
                badges_row.setSpacing(6)
                for badge in raw_badges:
                    label = str(badge or "").strip()
                    if not label:
                        continue
                    badge_label = QLabel(label)
                    badge_label.setProperty("ui_role", "list_item_badge")
                    badge_label.setStyleSheet(
                        "background-color: #E2E8F0; color: #1E293B; border-radius: 8px; padding: 1px 6px; font-size: 11px;"
                    )
                    badges_row.addWidget(badge_label, 0, Qt.AlignmentFlag.AlignLeft)
                badges_row.addStretch(1)
                text_col.addLayout(badges_row)

        body = QLabel(str(item_ctx.get("text") or ""))
        body.setProperty("ui_role", "list_item_text")
        body.setWordWrap(True)
        text_col.addWidget(body)

        row.addLayout(text_col, 1)
        return base

    def _build_item_widget(
        self, container: QFrame, item_ctx: dict, index: int
    ) -> QWidget | None:
        template = container.props.get("itemTemplate")  # type: ignore[attr-defined]
        if template:
            item_template = copy.deepcopy(template)
            self._make_ids_unique(item_template, str(index))
            return container.app_instance.renderer.build_widget(
                container.surface_id,
                container.app_instance.surfaces,
                comp_def=item_template,
                item=item_ctx,
                app_instance=container.app_instance,
            )

        template_name = str(container.props.get("template") or "").strip().lower()  # type: ignore[attr-defined]
        if template_name in {"text", "title_text"}:
            return self._build_default_item_widget(item_ctx, template_name)

        return None

    def _is_action_visible(
        self, container: QFrame, item_ctx: dict, action_def: dict
    ) -> bool:
        return spec_is_visible(action_def, container.app_instance, item_ctx)

    def _refresh_selected_action_button(self, container: QFrame):
        button = getattr(container, "_selected_action_button", None)
        if button is None:
            return

        selected_items = self._selected_items(container)
        count = len(selected_items)
        button.setEnabled(count > 0)

        action_spec = container.props.get("selectedItemsAction")  # type: ignore[attr-defined]
        explicit_label = container.props.get("selectedItemsActionLabel")  # type: ignore[attr-defined]
        base_label = "Apply to selected"
        if isinstance(action_spec, dict):
            action_label = action_spec.get("label")
            if isinstance(action_label, str) and action_label.strip():
                base_label = action_label.strip()
        if isinstance(explicit_label, str) and explicit_label.strip():
            base_label = explicit_label.strip()

        button.setText(f"{base_label} ({count})")

    def _evaluate_item_selectable(self, container: QFrame, item_ctx: dict) -> bool:
        list_selectable = _to_bool(container.props.get("selectable", False))  # type: ignore[attr-defined]
        if not list_selectable:
            return False

        if "selectable" not in item_ctx:
            return True

        selectable_rule = item_ctx.get("selectable")
        if isinstance(selectable_rule, dict):
            if (
                "conditions" in selectable_rule
                or "operator" in selectable_rule
                or "mode" in selectable_rule
            ):
                return self._evaluate_visibility_rule(
                    selectable_rule,
                    container.app_instance,
                    item_ctx,
                    default=False,
                )
            if (
                "left" in selectable_rule
                or "right" in selectable_rule
                or "value1" in selectable_rule
                or "value2" in selectable_rule
                or "op" in selectable_rule
            ):
                return self._evaluate_condition(
                    selectable_rule,
                    container.app_instance,
                    item_ctx,
                )
            return _to_bool(selectable_rule)

        return _to_bool(selectable_rule)

    def _populate_list(self, container, data_items):
        container._list_data_items = list(data_items or [])  # type: ignore[attr-defined]

        selected_keys = set(getattr(container, "_selected_item_keys", set()))
        available_keys = set()
        for index, raw in enumerate(container._list_data_items):  # type: ignore[attr-defined]
            item_ctx = raw if isinstance(raw, dict) else {"value": raw}
            if self._evaluate_item_selectable(container, item_ctx):
                available_keys.add(self._item_key(item_ctx, index))
        container._selected_item_keys = selected_keys.intersection(available_keys)  # type: ignore[attr-defined]

        layout = container.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.spacerItem():
                layout.removeItem(item)

        on_click = container.props.get("onItemClick")  # type: ignore[attr-defined]
        item_actions = container.props.get("itemActions")  # type: ignore[attr-defined]
        if not isinstance(item_actions, list):
            item_actions = []

        for i, item_data in enumerate(data_items):
            item_ctx = (
                item_data if isinstance(item_data, dict) else {"value": item_data}
            )
            key = self._item_key(item_ctx, i)
            selectable = self._evaluate_item_selectable(container, item_ctx)
            is_selected = key in container._selected_item_keys  # type: ignore[attr-defined]

            content_widget = self._build_item_widget(container, item_ctx, i)
            if content_widget is None:
                continue

            if "active" in item_ctx and hasattr(content_widget, "setProperty"):
                is_active = "true" if _to_bool(item_ctx.get("active")) else "false"
                content_widget.setProperty("active", is_active)
                content_widget.style().unpolish(content_widget)
                content_widget.style().polish(content_widget)

            row_frame = ListItemFrame()
            row_frame.setObjectName(f"{container.comp_id}_item_{i}")
            row_frame.setProperty("type", "list_item")
            row_frame.setProperty("item_index", i)
            row_frame.setProperty("selected", "true" if is_selected else "false")
            row_frame.setProperty("selectable", "true" if selectable else "false")
            row_frame.setAttribute(Qt.WA_StyledBackground)
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(6)

            checkbox = None
            show_checkbox = _to_bool(container.props.get("selectable", False))  # type: ignore[attr-defined]
            if show_checkbox:
                checkbox = QCheckBox()
                checkbox.setProperty("ui_role", "list_row_checkbox")
                checkbox.setChecked(is_selected)
                checkbox.setEnabled(selectable)
                checkbox.setCursor(Qt.PointingHandCursor)
                row_layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignVCenter)

            content_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            row_layout.addWidget(content_widget, 1)

            if item_actions:
                visible_actions = [
                    action_def
                    for action_def in item_actions
                    if isinstance(action_def, dict)
                    and self._is_action_visible(container, item_ctx, action_def)
                ]
            else:
                visible_actions = []

            if visible_actions:
                menu_button = QToolButton()
                menu_button.setCursor(Qt.PointingHandCursor)
                menu_button.setAutoRaise(True)
                menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
                icon_default = theme_token(
                    "icon.default",
                    app_instance=getattr(container, "app_instance", None),
                )
                menu_button.setIcon(get_icon("ric.more-2-fill", icon_default, 16))
                menu_button.setProperty("ui_role", "list_action_btn")
                menu = QMenu(menu_button)

                for action_def in visible_actions:
                    label = str(action_def.get("label") or "Action")
                    action_payload = action_def.get("action")
                    action_item = QAction(label, menu)
                    icon_name = str(action_def.get("icon") or "").strip()
                    if icon_name:
                        action_item.setIcon(
                            get_icon(normalize_icon_name(icon_name), icon_default, 14)
                        )
                    action_item.triggered.connect(
                        lambda _=False, payload=action_payload, data=dict(
                            item_ctx
                        ), idx=i: self._emit_action(
                            container,
                            payload,
                            item=data,
                            extra={"item": data, "item_index": idx},
                        )
                    )
                    menu.addAction(action_item)

                menu_button.setMenu(menu)
                row_layout.addWidget(menu_button, 0, Qt.AlignmentFlag.AlignTop)

            def set_selection(
                selected_state: bool, item_key=key, frame=row_frame, cbox=checkbox
            ):
                if selected_state:
                    container._selected_item_keys.add(item_key)  # type: ignore[attr-defined]
                else:
                    container._selected_item_keys.discard(item_key)  # type: ignore[attr-defined]

                frame.setProperty("selected", "true" if selected_state else "false")
                frame.style().unpolish(frame)
                frame.style().polish(frame)

                if cbox is not None and cbox.isChecked() != selected_state:
                    cbox.blockSignals(True)
                    cbox.setChecked(selected_state)
                    cbox.blockSignals(False)

                self._refresh_selected_action_button(container)

            if checkbox is not None and selectable:
                checkbox.stateChanged.connect(
                    lambda state, fn=set_selection: fn(_is_checked_state(state))
                )

            def handle_row_click(
                data=item_ctx,
                selectable_item=selectable,
                item_key=key,
                idx=i,
                toggle_fn=set_selection,
            ):
                if (
                    _to_bool(container.props.get("selectable", False))
                    and selectable_item
                ):
                    currently_selected = item_key in container._selected_item_keys  # type: ignore[attr-defined]
                    toggle_fn(not currently_selected)
                    return
                if on_click:
                    self._emit_action(
                        container,
                        on_click,
                        item=data,
                        extra={"item": data, "item_index": idx},
                    )

            if selectable or on_click:
                row_frame.setCursor(Qt.PointingHandCursor)
                row_frame._on_primary_click = handle_row_click

            layout.addWidget(row_frame)

        selected_action = container.props.get("selectedItemsAction")  # type: ignore[attr-defined]
        list_selectable = _to_bool(container.props.get("selectable", False))  # type: ignore[attr-defined]
        if selected_action and list_selectable:
            action_button = QPushButton()
            action_button.setObjectName(f"{container.comp_id}_selected_action")
            action_button.setCursor(Qt.PointingHandCursor)

            def dispatch_selected_action():
                selected_items = self._selected_items(container)
                if not selected_items:
                    return
                self._emit_action(
                    container,
                    selected_action,
                    item={
                        "selected_items": selected_items,
                        "selected_count": len(selected_items),
                        "selected_ids": [
                            item.get("id")
                            for item in selected_items
                            if isinstance(item, dict)
                        ],
                    },
                    extra={
                        "selected_items": selected_items,
                        "selected_count": len(selected_items),
                        "selected_ids": [
                            item.get("id")
                            for item in selected_items
                            if isinstance(item, dict)
                        ],
                    },
                )

            action_button.clicked.connect(dispatch_selected_action)
            layout.addWidget(action_button, 0, Qt.AlignmentFlag.AlignLeft)
            container._selected_action_button = action_button  # type: ignore[attr-defined]
            self._refresh_selected_action_button(container)
        else:
            container._selected_action_button = None  # type: ignore[attr-defined]
