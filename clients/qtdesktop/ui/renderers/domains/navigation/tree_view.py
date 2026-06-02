from __future__ import annotations

from typing import Any, Dict
import time

from PySide6.QtCore import Qt, QObject, QEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
    QSizePolicy,
)

from ...base import BaseRenderer, confirm_action, emit_action_spec
from ...icon import get_icon, normalize_icon_name
from ....theme.tokens import theme_token
from shiboken6 import isValid


class TreeCursorPointerEffect(QObject):
    def __init__(self, tree: QTreeWidget):
        super().__init__(tree)
        self.tree = tree
        self.viewport = tree.viewport()

        self.viewport.setMouseTracking(True)
        self.viewport.installEventFilter(self)

        tree.destroyed.connect(self._on_tree_destroyed)
        self.viewport.destroyed.connect(self._on_viewport_destroyed)

    def _on_tree_destroyed(self):
        self.tree = None

    def _on_viewport_destroyed(self):
        self.viewport = None

    def eventFilter(self, obj, event):
        if self.tree is None or self.viewport is None:
            return False

        if not isValid(self.tree) or not isValid(self.viewport):
            return False

        if obj is not self.viewport:
            return False

        if event.type() == QEvent.Type.MouseMove:
            item = self.tree.itemAt(event.pos())
            if item is not None:
                self.viewport.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.viewport.setCursor(Qt.CursorShape.ArrowCursor)

        elif event.type() == QEvent.Type.Leave:
            self.viewport.setCursor(Qt.CursorShape.ArrowCursor)

        return False


class TreeViewRenderer(BaseRenderer):
    component_type = "TreeView"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "nodes": self.PROPERTY,
            "action": self.COMPONENT,
            "click_action": self.COMPONENT,
            "select_action": self.COMPONENT,
            "params": self.COMPONENT,
            "expand_all": self.COMPONENT,
            "selection_mode": self.COMPONENT,
            "click_mode": self.COMPONENT,
            "active_id": self.PROPERTY,
            "active_as_selection": self.COMPONENT,
        }

    def _get_expanded_ids(self, tree: QTreeWidget) -> set[str]:
        expanded = set()
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        iterator = QTreeWidgetItemIterator(tree)
        while iterator.value():
            item = iterator.value()
            if item.isExpanded():
                payload = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(payload, dict) and "id" in payload:
                    expanded.add(str(payload["id"]))
            iterator += 1
        return expanded

    def _apply_expanded_ids(self, tree: QTreeWidget, expanded: set[str]):
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        iterator = QTreeWidgetItemIterator(tree)
        while iterator.value():
            item = iterator.value()
            payload = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(payload, dict) and str(payload.get("id")) in expanded:
                item.setExpanded(True)
            iterator += 1

    def _extract_condition_paths(self, rule: Any) -> set[str]:
        from ...base import extract_store_path

        paths = set()
        if not isinstance(rule, dict):
            return paths

        # Check if it's a single condition
        path = extract_store_path(rule.get("left"))
        if path:
            paths.add(path)
        path = extract_store_path(rule.get("right"))
        if path:
            paths.add(path)

        # Check if it's a rule with sub-conditions
        for cond in rule.get("conditions", []):
            paths.update(self._extract_condition_paths(cond))

        return paths

    def _collect_all_condition_paths(self, nodes: list[dict]) -> set[str]:
        paths = set()
        for node in nodes:
            if not isinstance(node, dict):
                continue
            active_rule = node.get("active")
            if active_rule:
                paths.update(self._extract_condition_paths(active_rule))
            children = node.get("children", [])
            if isinstance(children, list) and children:
                paths.update(self._collect_all_condition_paths(children))
        return paths

    def _evaluate_node_active(self, node: dict, app_instance: Any) -> bool:
        rule = node.get("active")
        if rule is None:
            return False
        if isinstance(rule, bool):
            return rule
        if not isinstance(rule, dict):
            return bool(rule)

        # If it's a rule (has 'operator' or 'conditions'), use visibility logic
        if "conditions" in rule or "operator" in rule or "mode" in rule:
            return self._evaluate_visibility_rule(
                rule, app_instance, node, default=False
            )

        # Otherwise treat as single condition
        return self._evaluate_condition(rule, app_instance, node)

    def _normalize_active_ids(self, active_value: Any) -> set[str]:
        if active_value is None:
            return set()
        if isinstance(active_value, (list, tuple, set)):
            return {str(v) for v in active_value if v is not None and str(v) != ""}
        value = str(active_value)
        return {value} if value else set()

    def _set_item_active_visual(self, item: QTreeWidgetItem, is_active: bool) -> None:
        # Keep active state visually distinct from selection.
        f = item.font(0)
        f.setBold(bool(is_active))
        item.setFont(0, f)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, bool(is_active))

    def _node_selectable(self, node: dict, has_children: bool) -> bool:
        selectable_override = node.get("selectable")
        if selectable_override is None:
            return not has_children
        return bool(selectable_override)

    def _node_payload(
        self,
        node: dict,
        node_id: str,
        label: str,
        *,
        is_selectable: bool,
        is_disabled: bool,
    ) -> dict[str, Any]:
        return {
            "id": node_id,
            "label": label,
            "value": node.get("value"),
            "path": node.get("path"),
            "meta": node.get("meta"),
            "active": node.get("active"),
            "selectable": is_selectable,
            "disabled": is_disabled,
        }

    def _payload_interactive(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if bool(payload.get("disabled", False)):
            return False
        return bool(payload.get("selectable", True))

    def _item_or_descendant_active(self, item: QTreeWidgetItem) -> bool:
        if bool(item.data(0, Qt.ItemDataRole.UserRole + 1)):
            return True
        for i in range(item.childCount()):
            if self._item_or_descendant_active(item.child(i)):
                return True
        return False

    def _sync_active_selection(
        self, tree: QTreeWidget, active_item: QTreeWidgetItem | None
    ) -> None:
        if not bool(getattr(tree, "_active_as_selection", False)):
            return
        if tree.selectionMode() == QAbstractItemView.SelectionMode.NoSelection:
            return
        tree.blockSignals(True)
        try:
            tree.clearSelection()
            if active_item is not None:
                active_item.setSelected(True)
                tree.setCurrentItem(active_item)
        finally:
            tree.blockSignals(False)

    def _apply_node_activations(
        self, tree: QTreeWidget, app_instance: Any
    ) -> QTreeWidgetItem | None:
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        global_active_ids = set(getattr(tree, "_tree_active_ids", set()) or set())
        first_active_item = None
        iterator = QTreeWidgetItemIterator(tree)
        while iterator.value():
            item = iterator.value()
            node = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(node, dict):
                node_id = str(node.get("id") or "")
                is_active = self._evaluate_node_active(
                    node, app_instance
                ) or node_id in global_active_ids
                self._set_item_active_visual(item, is_active)
                if is_active:
                    curr = item.parent()
                    while curr:
                        curr.setExpanded(True)
                        curr = curr.parent()
                    if first_active_item is None:
                        first_active_item = item
            iterator += 1
        if first_active_item is not None:
            tree.scrollToItem(first_active_item)
        self._sync_active_selection(tree, first_active_item)
        return first_active_item

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        tree = QTreeWidget()
        tree.setObjectName(comp_id)
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        tree.setColumnCount(1)
        tree.setStyleSheet("")

        tree.setAlternatingRowColors(False)
        tree.setAnimated(True)
        tree.setProperty("ui_role", "tree_container")
        tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        min_height = props.get("min_height", 100)
        tree.setMinimumHeight(min_height)

        if props.get("full_height", False):
            tree.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

        selection_mode = str(props.get("selection_mode", "single")).strip().lower()
        if selection_mode == "none":
            tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        elif selection_mode == "multiple":
            tree.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        else:
            tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        click_mode = str(props.get("click_mode", "single")).strip().lower()
        use_double_activation_fallback = click_mode == "double"
        if click_mode == "none":
            mapped_click = tree.itemClicked
        elif click_mode == "double":
            mapped_click = tree.itemDoubleClicked
        else:
            mapped_click = tree.itemClicked

        nodes = props.get("nodes", [])
        click_action = props.get("click_action") or props.get("action", "")
        select_action = props.get("select_action", "")
        click_action_name = self._action_name(click_action)
        select_action_name = self._action_name(select_action)
        base_params = props.get("params", {})
        if not isinstance(base_params, dict):
            base_params = {}

        # State Preservation
        if not hasattr(app_instance, "_tree_expansion_cache"):
            app_instance._tree_expansion_cache = {}
        if not hasattr(app_instance, "_tree_selection_cache"):
            app_instance._tree_selection_cache = {}

        state_key = f"{surface_id}:{comp_id}"
        cached_expanded = app_instance._tree_expansion_cache.get(state_key, set())
        cached_selected = app_instance._tree_selection_cache.get(state_key, set())

        tree._tree_active_ids = self._normalize_active_ids(props.get("active_id"))
        tree._active_as_selection = bool(props.get("active_as_selection", False))
        tree._tree_confirmed_selection = set(cached_selected)

        def _populate(
            items: list[dict], parent_item: QTreeWidgetItem | None = None
        ) -> None:
            for index, node in enumerate(items):
                if not isinstance(node, dict):
                    continue
                node_id = str(node.get("id") or f"node_{index}")
                label = str(node.get("label") or node_id)

                item = QTreeWidgetItem([label])

                icon_name = node.get("icon")
                if icon_name:
                    item.setIcon(
                        0,
                        get_icon(
                            normalize_icon_name(icon_name),
                            theme_token("text.primary", app_instance=app_instance),
                        ),
                    )

                children = node.get("children", [])
                has_children = isinstance(children, list) and len(children) > 0
                is_disabled = bool(node.get("disabled", False))
                is_selectable = self._node_selectable(node, has_children)
                item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    self._node_payload(
                        node,
                        node_id,
                        label,
                        is_selectable=is_selectable,
                        is_disabled=is_disabled,
                    ),
                )
                item.setDisabled(is_disabled)
                if not is_selectable:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

                if parent_item is None:
                    tree.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)

                # Restore expansion: Cache > Prop (must be after adding to tree)
                is_expanded = node_id in cached_expanded or bool(
                    node.get("expanded", False)
                )
                item.setExpanded(is_expanded)

                # Restore selection from UI cache only.
                if node_id in cached_selected:
                    item.setSelected(True)

                if isinstance(children, list) and children:
                    _populate(children, item)

        _populate(nodes if isinstance(nodes, list) else [])

        if click_action_name:
            tree._hover_effect = TreeCursorPointerEffect(tree)
            last_emit = {"ts": 0.0, "id": ""}

            def _emit_action(item: QTreeWidgetItem, _column: int) -> None:
                # Avoid duplicate emits when both double-click and activated fire.
                payload = item.data(0, Qt.ItemDataRole.UserRole) or {}
                if not self._payload_interactive(payload):
                    return
                payload_id = ""
                if isinstance(payload, dict):
                    payload_id = str(payload.get("id") or "")
                now = time.monotonic()
                if payload_id and last_emit["id"] == payload_id and (now - last_emit["ts"]) < 0.25:
                    return
                last_emit["id"] = payload_id
                last_emit["ts"] = now

                # Capture snapshot before action (to survive re-render)
                app_instance._tree_expansion_cache[state_key] = self._get_expanded_ids(
                    tree
                )
                app_instance._tree_selection_cache[state_key] = {
                    str(i.data(0, Qt.ItemDataRole.UserRole).get("id"))
                    for i in tree.selectedItems()
                    if isinstance(i.data(0, Qt.ItemDataRole.UserRole), dict)
                }
                context = dict(base_params)
                if isinstance(payload, dict):
                    context.update(payload)
                emit_action_spec(
                    app_instance, click_action, context, surface_id, comp_id
                )

            if click_mode != "none":
                mapped_click.connect(_emit_action)
                if use_double_activation_fallback:
                    tree.itemActivated.connect(_emit_action)

        if select_action_name:
            tree._hover_effect = TreeCursorPointerEffect(tree)

            def _emit_selection_change_action() -> None:
                items = tree.selectedItems()
                # Capture snapshot before action (to survive re-render)
                app_instance._tree_expansion_cache[state_key] = self._get_expanded_ids(
                    tree
                )

                selected_ids = set()
                for item in items:
                    p = item.data(0, Qt.ItemDataRole.UserRole)
                    if self._payload_interactive(p) and "id" in p:
                        selected_ids.add(str(p["id"]))

                full_payload = []
                for item in items:
                    payload = item.data(0, Qt.ItemDataRole.UserRole) or {}
                    if self._payload_interactive(payload):
                        full_payload.append(payload)

                context = dict(base_params)
                context["selected_items"] = full_payload
                if not full_payload:
                    return
                active_payload = full_payload[-1]
                if active_payload.get("id"):
                    context["active_id"] = str(active_payload.get("id"))

                confirm = select_action.get("confirm") if isinstance(select_action, dict) else None
                if select_action and not confirm_action(app_instance, confirm):
                    previous = getattr(tree, "_tree_confirmed_selection", set())
                    tree.blockSignals(True)
                    try:
                        tree.clearSelection()
                        from PySide6.QtWidgets import QTreeWidgetItemIterator

                        iterator = QTreeWidgetItemIterator(tree)
                        while iterator.value():
                            item = iterator.value()
                            payload = item.data(0, Qt.ItemDataRole.UserRole)
                            if isinstance(payload, dict) and str(payload.get("id") or "") in previous:
                                item.setSelected(True)
                            iterator += 1
                    finally:
                        tree.blockSignals(False)
                    return

                app_instance._tree_selection_cache[state_key] = selected_ids
                tree._tree_confirmed_selection = set(selected_ids)
                action_spec = select_action
                if isinstance(action_spec, dict):
                    action_spec = dict(action_spec)
                    action_spec.pop("confirm", None)
                emit_action_spec(
                    app_instance, action_spec, context, surface_id, comp_id
                )

            tree.itemSelectionChanged.connect(_emit_selection_change_action)

        if bool(props.get("expand_all", False)):
            tree.expandAll()

        # Apply active state (rules + active_id), optionally syncing to selection.
        self._apply_node_activations(tree, app_instance)

        def _keep_active_branch_expanded(item: QTreeWidgetItem) -> None:
            # Refresh active flags before checking descendants, to avoid stale state.
            self._apply_node_activations(tree, app_instance)
            if self._item_or_descendant_active(item):
                item.setExpanded(True)

        tree.itemCollapsed.connect(_keep_active_branch_expanded)

        # Reactive Bindings for per-node 'active' conditions
        all_paths = self._collect_all_condition_paths(
            nodes if isinstance(nodes, list) else []
        )
        if all_paths:

            def _update_activations():
                if isValid(tree):
                    self._apply_node_activations(tree, app_instance)

            app_instance.binder.bind_many(
                list(all_paths), _update_activations, owner=tree
            )

        return tree

    def _action_name(self, action: Any) -> str:
        if isinstance(action, dict):
            return str(action.get("name") or "").strip()
        return str(action or "").strip()

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if not isinstance(widget, QTreeWidget):
            return super().update_widget_property(widget, prop, value)

        if prop == "nodes":
            app_instance = widget.property("_app_instance") or widget.window()
            # Save current expansion/selection state (re-use same logic as snapshot)
            expanded = self._get_expanded_ids(widget)
            selected = {
                str(i.data(0, Qt.ItemDataRole.UserRole).get("id"))
                for i in widget.selectedItems()
                if isinstance(i.data(0, Qt.ItemDataRole.UserRole), dict)
            }



            # Block signals during reconstruction to prevent snapshot corruption
            widget.blockSignals(True)
            try:
                widget.clear()

                # Recursive populate helper
                def _populate(items, parent, app_ptr):
                    for index, node in enumerate(items):
                        if not isinstance(node, dict):
                            continue
                        node_id = str(node.get("id") or f"node_{index}")
                        item = QTreeWidgetItem([str(node.get("label") or node_id)])

                        icon_name = node.get("icon")
                        if icon_name:
                            item.setIcon(
                                0, get_icon(normalize_icon_name(icon_name), "#fff")
                            )

                        children = node.get("children", [])
                        has_children = isinstance(children, list) and len(children) > 0
                        is_disabled = bool(node.get("disabled", False))
                        is_selectable = self._node_selectable(node, has_children)
                        item.setData(
                            0,
                            Qt.ItemDataRole.UserRole,
                            self._node_payload(
                                node,
                                node_id,
                                str(node.get("label") or node_id),
                                is_selectable=is_selectable,
                                is_disabled=is_disabled,
                            ),
                        )
                        item.setDisabled(is_disabled)
                        if not is_selectable:
                            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

                        if parent is None:
                            widget.addTopLevelItem(item)
                        else:
                            parent.addChild(item)

                        # Restore expansion
                        if node_id in expanded:
                            item.setExpanded(True)

                        # Restore selection from cache only.
                        if node_id in selected:
                            item.setSelected(True)

                        if isinstance(children, list) and children:
                            _populate(children, item, app_ptr)

                _populate(value if isinstance(value, list) else [], None, app_instance)
                self._apply_node_activations(widget, app_instance)

                # Update reactive bindings for new nodes
                all_paths = self._collect_all_condition_paths(
                    value if isinstance(value, list) else []
                )
                if all_paths:

                    def _update_activations(app_ptr=app_instance):
                        if isValid(widget):
                            self._apply_node_activations(widget, app_ptr)

                    app_instance.binder.bind_many(
                        list(all_paths), _update_activations, owner=widget
                    )
            finally:
                widget.blockSignals(False)
            return

        if prop == "active_id":
            app_instance = widget.property("_app_instance") or widget.window()
            widget._tree_active_ids = self._normalize_active_ids(value)
            self._apply_node_activations(widget, app_instance)
            return

        super().update_widget_property(widget, prop, value)
