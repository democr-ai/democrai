from PySide6.QtWidgets import (
    QLabel,
    QCheckBox,
    QWidget,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QVBoxLayout,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
)
from PySide6.QtCore import Qt
from typing import Dict, Any
from ...base import (
    BaseRenderer,
    confirm_action,
    emit_action_spec,
    publish_bound_value,
)
import os

class FolderSelectorRenderer(BaseRenderer):
    component_type = "FolderSelector"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "value": self.PROPERTY,
            "label": self.SURFACE,
            "placeholder": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        label_text = props.get("label", "Select Folder")
        value = props.get("value", "")
        placeholder = props.get("placeholder", "Path...")
        action = props.get("action")

        container = QWidget()
        container.setObjectName(comp_id + "_container")

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        if label_text:
            lbl = QLabel(label_text)
            lbl.setProperty("ui_role", "folder_label")
            main_layout.addWidget(lbl)

        row_container = QWidget()
        row_layout = QHBoxLayout(row_container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)

        line_edit = QLineEdit(value)
        line_edit.setPlaceholderText(placeholder)
        line_edit.setReadOnly(True)
        line_edit.setObjectName(comp_id)
        line_edit.setProperty("is_input", True)
        line_edit.setProperty("ui_role", "folder_input")
        row_layout.addWidget(line_edit, 1)
        container.setProperty("value", value)
        container.setProperty("_confirmed_value", value)
        publish_bound_value(app_instance, line_edit, comp_id, value)

        btn = QPushButton("Browse…")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("ui_role", "folder_browse_btn")

        def pick_folder():
            folder = QFileDialog.getExistingDirectory(
                container, "Select Folder", value or os.path.expanduser("~")
            )
            if folder:
                previous = str(container.property("_confirmed_value") or "")
                confirm = action.get("confirm") if isinstance(action, dict) else None
                if action and not confirm_action(app_instance, confirm):
                    line_edit.setText(previous)
                    container.setProperty("value", previous)
                    return
                line_edit.setText(folder)
                container.setProperty("value", folder)
                container.setProperty("_confirmed_value", folder)
                publish_bound_value(app_instance, line_edit, comp_id, folder)
                if action:
                    action_spec = action
                    if isinstance(action, dict):
                        action_spec = dict(action)
                        action_spec.pop("confirm", None)
                    emit_action_spec(
                        app_instance,
                        action_spec,
                        {comp_id: folder, "value": folder},
                        surface_id,
                        comp_id,
                    )

        btn.clicked.connect(pick_folder)
        row_layout.addWidget(btn)

        main_layout.addWidget(row_container)

        return container

    def update_widget_property(self, widget: QWidget, prop: str, value: Any):
        if prop == "value":
            # Find the line edit child
            line_edit = widget.findChild(QLineEdit)
            if line_edit and line_edit.text() != str(value):
                line_edit.blockSignals(True)
                line_edit.setText(str(value))
                line_edit.blockSignals(False)
            widget.setProperty("value", str(value))
            widget.setProperty("_confirmed_value", str(value))
        elif prop == "placeholder":
            line_edit = widget.findChild(QLineEdit)
            if line_edit:
                line_edit.setPlaceholderText("" if value is None else str(value))
        else:
            super().update_widget_property(widget, prop, value)

    def setup_bindings(self, widget: QWidget, props: Dict[str, Any]):
        store = getattr(widget.window(), "store", None)
        if store is None:
            return
        # Specific binding for internal LineEdit
        if "value" in props:
            val = props["value"]
            if isinstance(val, str) and (
                val.startswith("$state.") or val.startswith("$global.")
            ):
                key = val.replace("$state.", "").replace("$global.", "")
                line_edit = widget.findChild(QLineEdit)
                if line_edit:
                    line_edit.textChanged.connect(
                        lambda text, k=key: store.set(k, text, "page")
                    )
