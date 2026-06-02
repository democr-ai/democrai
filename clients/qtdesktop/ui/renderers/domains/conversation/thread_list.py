from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QTextEdit, QWidget
from ...base import BaseRenderer, confirm_action, emit_action_spec, publish_bound_value
from ...collection_patch import patch_collection

class ThreadListRenderer(BaseRenderer):
    component_type = "ThreadList"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "threads": self.COMPONENT,
            "active_thread_id": self.PROPERTY,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        widget = QListWidget()
        widget.setObjectName(comp_id)
        widget.setProperty("ui_role", "advanced_thread_list")
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        action = props.get("action")
        active_id = str(props.get("active_thread_id", ""))
        threads = list(props.get("threads", []))
        widget._threads = threads  # type: ignore[attr-defined]
        widget._confirmed_active_thread_id = active_id  # type: ignore[attr-defined]
        for index, thread in enumerate(threads):
            item = QListWidgetItem(str(thread.get("title", f"Thread {index + 1}")))
            item.setData(Qt.ItemDataRole.UserRole, thread)
            item.setToolTip(str(thread.get("snippet", "")))
            widget.addItem(item)
            if str(thread.get("id", "")) == active_id:
                widget.setCurrentItem(item)

        def on_select(item: QListWidgetItem):
            thread = item.data(Qt.ItemDataRole.UserRole) or {}
            thread_id = str(thread.get("id", ""))
            confirm = action.get("confirm") if isinstance(action, dict) else None
            if action and not confirm_action(app_instance, confirm):
                previous = str(getattr(widget, "_confirmed_active_thread_id", ""))
                widget.blockSignals(True)
                try:
                    for index in range(widget.count()):
                        candidate = widget.item(index)
                        candidate_thread = candidate.data(Qt.ItemDataRole.UserRole) or {}
                        if str(candidate_thread.get("id", "")) == previous:
                            widget.setCurrentItem(candidate)
                            break
                    else:
                        widget.clearSelection()
                finally:
                    widget.blockSignals(False)
                return
            publish_bound_value(
                app_instance,
                widget,
                comp_id,
                thread_id,
                prop_name="active_thread_id",
            )
            widget._confirmed_active_thread_id = thread_id  # type: ignore[attr-defined]
            if action:
                action_spec = action
                if isinstance(action_spec, dict):
                    action_spec = dict(action_spec)
                    action_spec.pop("confirm", None)
                emit_action_spec(
                    app_instance,
                    action_spec,
                    {"threadId": thread_id, "thread": thread},
                    surface_id,
                    comp_id,
                )

        widget.itemClicked.connect(on_select)
        return widget

    def apply_collection_patch(
        self,
        widget: QWidget,
        prop: str,
        action: str,
        value: Any,
    ) -> bool:
        if prop != "threads":
            return False
        threads = list(getattr(widget, "_threads", []))

        def make_item(thread: dict[str, Any], index_hint: int) -> QListWidgetItem:
            item = QListWidgetItem(str(thread.get("title", f"Thread {index_hint + 1}")))
            item.setData(Qt.ItemDataRole.UserRole, thread)
            item.setToolTip(str(thread.get("snippet", "")))
            return item

        patch = patch_collection(threads, action, value)
        if not patch.handled:
            return False

        if action == "append":
            for thread in (patch.appended or []):
                threads.append(thread)
                widget.addItem(make_item(thread, len(threads) - 1))
            widget._threads = threads  # type: ignore[attr-defined]
            return True

        if action == "remove":
            index = patch.index
            if index is None:
                return True
            threads.pop(index)
            item = widget.takeItem(index)
            del item
            widget._threads = threads  # type: ignore[attr-defined]
            return True

        if action == "replace":
            index = patch.index
            replacement = patch.replacement
            if index is None or replacement is None:
                return True
            threads[index] = replacement
            item = widget.item(index)
            if item is not None:
                item.setText(str(replacement.get("title", f"Thread {index + 1}")))
                item.setData(Qt.ItemDataRole.UserRole, replacement)
                item.setToolTip(str(replacement.get("snippet", "")))
            widget._threads = threads  # type: ignore[attr-defined]
            return True

        if action == "set":
            threads = list(patch.items)
            widget.clear()
            for index, thread in enumerate(threads):
                widget.addItem(make_item(thread, index))
            widget._threads = threads  # type: ignore[attr-defined]
            return True
        return True

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "active_thread_id":
            target = str(value or "")
            for index in range(widget.count()):
                item = widget.item(index)
                thread = item.data(Qt.ItemDataRole.UserRole) or {}
                if str(thread.get("id", "")) == target:
                    widget.setCurrentItem(item)
                    widget._confirmed_active_thread_id = target  # type: ignore[attr-defined]
                    break
            return
        super().update_widget_property(widget, prop, value)
