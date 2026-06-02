from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...base import BaseRenderer, emit_action_spec
from ...collection_patch import patch_collection


def _clear_layout(layout: QVBoxLayout | QHBoxLayout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        nested = child.layout()
        if nested is not None:
            _clear_layout(nested)  # type: ignore[arg-type]
            continue
        widget = child.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class WizardRenderer(BaseRenderer):
    component_type = "Wizard"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "steps": self.PROPERTY,
            "active_step_id": self.PROPERTY,
            "validated_steps": self.PROPERTY,
            "action": self.COMPONENT,
            "params": self.COMPONENT,
            "allow_step_click": self.PROPERTY,
            "show_controls": self.PROPERTY,
            "prev_label": self.PROPERTY,
            "next_label": self.PROPERTY,
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
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        root._wizard_props = dict(props)  # type: ignore[attr-defined]
        root._wizard_surface_id = surface_id  # type: ignore[attr-defined]
        root._wizard_app = app_instance  # type: ignore[attr-defined]
        root._wizard_comp_id = comp_id  # type: ignore[attr-defined]
        self._build(root)
        return root

    def _build(self, widget: QWidget) -> None:
        props = dict(getattr(widget, "_wizard_props", {}))
        surface_id = getattr(widget, "_wizard_surface_id", "main")
        app_instance = getattr(widget, "_wizard_app", None)
        comp_id = getattr(widget, "_wizard_comp_id", widget.objectName())
        if app_instance is None:
            return

        layout = widget.layout()
        if layout is None:
            return
        _clear_layout(layout)

        raw_steps = props.get("steps", [])
        steps = raw_steps if isinstance(raw_steps, list) else []
        if not steps:
            empty = QLabel("No steps configured.")
            empty.setProperty("ui_role", "wizard_empty")
            layout.addWidget(empty)
            return

        active = str(props.get("active_step_id") or "")
        if not active:
            active = str(steps[0].get("id") or "")
        step_ids = [str(step.get("id") or f"step_{idx+1}") for idx, step in enumerate(steps)]
        if active not in step_ids and step_ids:
            active = step_ids[0]
        raw_validated = props.get("validated_steps", [])
        validated_steps = raw_validated if isinstance(raw_validated, list) else []

        action = props.get("action")
        if isinstance(action, dict):
            action_name = str(action.get("name") or "").strip()
        else:
            action_name = str(action or "").strip()
        raw_params = props.get("params", {})
        base_params = dict(raw_params) if isinstance(raw_params, dict) else {}
        wizard_id = str(
            base_params.get("target_wizard")
            or base_params.get("wizard_id")
            or comp_id
            or ""
        ).strip()
        if wizard_id:
            base_params["wizard_id"] = wizard_id
            base_params["target_wizard"] = wizard_id
        base_params["steps"] = [dict(step) for step in steps if isinstance(step, dict)]
        base_params["active_step_id"] = active
        base_params["validated_steps"] = [str(item) for item in validated_steps if str(item).strip()]

        # Prefer concrete wizard actions on desktop to avoid relying on dispatch fan-out.
        action_step_click = action
        action_prev = action
        action_next = action
        if action_name.endswith("wizard_dispatch"):
            prefix = action_name[: -len("wizard_dispatch")]
            action_step_click = self._with_action_name(action, f"{prefix}wizard_go_to")
            action_prev = self._with_action_name(action, f"{prefix}wizard_prev")
            action_next = self._with_action_name(action, f"{prefix}wizard_next")
        allow_step_click = bool(props.get("allow_step_click", True))

        step_bar = QHBoxLayout()
        step_bar.setContentsMargins(0, 0, 0, 0)
        step_bar.setSpacing(8)

        active_index = next(
            (i for i, s in enumerate(steps) if str(s.get("id") or f"step_{i+1}") == active),
            0,
        )
        validated_set = {str(item) for item in validated_steps if str(item).strip()}
        for idx, step in enumerate(steps):
            step_id = step_ids[idx]
            title = str(step.get("title") or step_id)
            status = str(step.get("status") or "")
            if not status:
                if step_id in validated_set:
                    status = "done"
                elif idx == active_index:
                    status = "current"
                elif any(prev_id not in validated_set for prev_id in step_ids[:idx]):
                    status = "locked"
                else:
                    status = "pending"
            btn = QPushButton(title)
            btn.setProperty("ui_role", "wizard_step_btn")
            btn.setProperty("active", step_id == active)
            btn.setProperty("status", status)
            btn.setProperty("appearance", "default" if step_id == active else "outline")
            btn.setCheckable(False)
            can_click_step = allow_step_click
            btn.setEnabled(can_click_step or step_id == active)
            if action_name and can_click_step:
                btn.clicked.connect(
                    lambda _=False, sid=step_id, index=idx: emit_action_spec(
                        app_instance,
                        action_step_click,
                        {
                            **base_params,
                            "step_id": sid,
                            "step_index": index,
                        },
                        surface_id,
                        comp_id,
                    )
                )
            step_bar.addWidget(btn)
            if idx < len(steps) - 1:
                sep = QLabel("›")
                sep.setProperty("ui_role", "wizard_sep")
                step_bar.addWidget(sep)
        step_bar.addStretch()
        layout.addLayout(step_bar)

        current_step = steps[active_index]
        body = QFrame()
        body.setProperty("ui_role", "wizard_body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(8)

        body_title = QLabel(str(current_step.get("title") or ""))
        body_title.setProperty("ui_role", "wizard_body_title")
        body_layout.addWidget(body_title)

        desc_text = str(current_step.get("description") or "")
        if desc_text:
            desc = QLabel(desc_text)
            desc.setWordWrap(True)
            desc.setProperty("ui_role", "wizard_body_desc")
            body_layout.addWidget(desc)

        content_text = str(current_step.get("content") or "")
        if content_text:
            content = QLabel(content_text)
            content.setWordWrap(True)
            content.setProperty("ui_role", "wizard_body_content")
            body_layout.addWidget(content)

        layout.addWidget(body)

        if bool(props.get("show_controls", True)):
            controls = QHBoxLayout()
            controls.setContentsMargins(0, 0, 0, 0)
            controls.setSpacing(8)

            prev_label = str(props.get("prev_label") or "Previous")
            next_label = str(props.get("next_label") or "Next")
            prev_btn = QPushButton(prev_label)
            next_btn = QPushButton(next_label)
            prev_btn.setProperty("ui_role", "wizard_prev_btn")
            prev_btn.setProperty("appearance", "outline")
            next_btn.setProperty("ui_role", "wizard_next_btn")
            next_btn.setProperty("appearance", "default")
            prev_btn.setEnabled(active_index > 0)
            can_go_next = active_index < len(steps) - 1
            next_btn.setEnabled(can_go_next)

            if action_name:
                prev_btn.clicked.connect(
                    lambda _=False: emit_action_spec(
                        app_instance,
                        action_prev,
                        {**base_params, "step_id": active},
                        surface_id,
                        comp_id,
                    )
                )
                next_btn.clicked.connect(
                    lambda _=False: emit_action_spec(
                        app_instance,
                        action_next,
                        {**base_params, "step_id": active},
                        surface_id,
                        comp_id,
                    )
                )
            controls.addWidget(prev_btn)
            controls.addWidget(next_btn)
            controls.addStretch()
            layout.addLayout(controls)

    def _with_action_name(self, action: Any, name: str) -> Any:
        if isinstance(action, dict):
            next_action = dict(action)
            next_action["name"] = name
            return next_action
        return name

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop in {
            "steps",
            "active_step_id",
            "validated_steps",
            "allow_step_click",
            "show_controls",
            "prev_label",
            "next_label",
            "action",
            "params",
        }:
            props = dict(getattr(widget, "_wizard_props", {}))
            props[prop] = value
            widget._wizard_props = props  # type: ignore[attr-defined]
            self._build(widget)
            return
        super().update_widget_property(widget, prop, value)

    def apply_collection_patch(
        self,
        widget: QWidget,
        prop: str,
        action: str,
        value: Any,
    ) -> bool:
        if prop != "steps":
            return False
        props = dict(getattr(widget, "_wizard_props", {}))
        current = list(props.get("steps", []))
        patch = patch_collection(current, action, value)
        if not patch.handled:
            return False
        props["steps"] = patch.items
        widget._wizard_props = props  # type: ignore[attr-defined]
        self._build(widget)
        return True
