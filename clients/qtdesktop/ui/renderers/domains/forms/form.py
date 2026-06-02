import re
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QSizePolicy,
    QFrame,
    QComboBox,
    QListWidget,
    QCheckBox,
    QAbstractButton,
    QButtonGroup,
    QSpacerItem,
)
from PySide6.QtCore import Qt
from typing import Dict, Any, List, Optional
from ...base import BaseRenderer, emit_action_spec
from .attachment import (
    AttachmentRenderer,
    _infer_module_name,
    upload_attachment_entries,
)
from .audio_recorder import AudioRecorderRenderer
from .checkbox import CheckboxRenderer
from .date_picker import DatePickerRenderer
from .editable_list import EditableListRenderer
from .radio_group import RadioGroupRenderer
from .select import SelectRenderer
from .tags_input import TagsInputRenderer
from .text_field import TextFieldRenderer
from .textarea import TextAreaRenderer
from .toggle import ToggleRenderer


def _separator():
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFixedHeight(1)
    sep.setProperty("ui_role", "form_separator")
    return sep


def _normalize_track_loading(value: Any, fallback_action_name: str = "") -> list[str]:
    names: list[str] = []
    if isinstance(value, (list, tuple, set)):
        names.extend(str(item or "").strip() for item in value)
    elif value is not None:
        raw = str(value).strip()
        if raw:
            names.append(raw)

    normalized = [name for name in names if name]
    if normalized:
        return normalized

    fallback = str(fallback_action_name or "").strip()
    return [fallback] if fallback else []


def _validate_field(
    field_def: dict, value: Any, values: Optional[Dict[str, Any]] = None
) -> str:
    """Return the first error message or empty string."""
    all_values = values or {}
    for v in field_def.get("validations", []):
        rule = v.get("rule")
        msg = v.get("message", "Invalid")

        if rule == "required":
            if field_def.get("type") == "checkbox":
                if not value:
                    return msg
            elif isinstance(value, list):
                if len(value) == 0:
                    return msg
            elif not value or (isinstance(value, str) and not value.strip()):
                return msg

        elif rule == "regex":
            pattern = v.get("pattern", "")
            if isinstance(value, str) and not re.match(pattern, value):
                return msg

        elif rule == "min_length":
            min_len = v.get("value", 0)
            if isinstance(value, str) and len(value) < min_len:
                return msg

        elif rule == "max_length":
            max_len = v.get("value", 0)
            if isinstance(value, str) and len(value) > max_len:
                return msg
        elif rule in {"equals_field", "same_as"}:
            other_field = str(v.get("field") or v.get("value") or "").strip()
            if not other_field:
                continue
            other_value = all_values.get(other_field)
            if value != other_value:
                return msg

    return ""


def _is_layout_node(node: dict) -> bool:
    return str(node.get("type", "")).lower() in {"row", "column"}


def _merge_initial_values(nodes: Any, values: Any) -> list[dict]:
    """Apply initial field values to a form model tree.

    This is intentionally used only at render-time initialization.
    """
    model_nodes = list(nodes) if isinstance(nodes, list) else []
    initial_values = values if isinstance(values, dict) else {}
    if not initial_values:
        return [dict(node) for node in model_nodes if isinstance(node, dict)]

    def _apply(node: dict) -> dict:
        updated = dict(node)
        if _is_layout_node(updated):
            children_key = (
                "children"
                if isinstance(updated.get("children"), list)
                else "items"
                if isinstance(updated.get("items"), list)
                else None
            )
            if children_key is not None:
                updated[children_key] = [
                    _apply(child) if isinstance(child, dict) else child
                    for child in list(updated.get(children_key) or [])
                ]
            return updated

        name = str(updated.get("name") or "").strip()
        if name and name in initial_values:
            updated["value"] = initial_values.get(name)
        return updated

    return [_apply(node) for node in model_nodes if isinstance(node, dict)]


def _get_by_path(obj: Any, path: str) -> Any:
    if not isinstance(obj, dict):
        return None
    current: Any = obj
    for segment in str(path or "").replace("/", ".").split("."):
        if not segment:
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


def _normalize_active(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def _resolve_form_operand(operand: Any, values: Dict[str, Any]) -> Any:
    if isinstance(operand, dict):
        operand_type = str(operand.get("type") or "").strip().lower()
        if operand_type == "form":
            value = _get_by_path(values, str(operand.get("path") or "").strip())
            return value if value is not None else operand.get("default")
        if operand_type == "literal":
            return operand.get("value", operand.get("default"))
        if "literalString" in operand:
            return operand.get("literalString")
        return operand

    if isinstance(operand, str) and operand.startswith("$form."):
        return _get_by_path(values, operand[6:])

    return operand


def _evaluate_form_condition(condition: Any, values: Dict[str, Any]) -> bool:
    if not isinstance(condition, dict):
        return False

    left = _resolve_form_operand(condition.get("left", condition.get("value1")), values)
    right = _resolve_form_operand(condition.get("right", condition.get("value2")), values)
    op = str(condition.get("op", condition.get("operator", "==")))

    try:
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "in":
            return left in right if isinstance(right, (list, tuple, set, str)) else False
        if op == "contains":
            return right in left if isinstance(left, (list, tuple, set, str)) else False
        if op == ">":
            return float(left) > float(right)
        if op == "<":
            return float(left) < float(right)
        if op == ">=":
            return float(left) >= float(right)
        if op == "<=":
            return float(left) <= float(right)
        if op == "matches":
            return re.search(str(right), str(left)) is not None
        if op == "exists":
            return left is not None
        if op == "empty":
            return left is None or left == "" or left == []
    except Exception:
        return False

    return False


def _evaluate_form_rule(rule: Any, values: Dict[str, Any], default: bool) -> bool:
    if rule is None:
        return default
    if isinstance(rule, str) and rule.startswith("$form."):
        return _normalize_active(_resolve_form_operand(rule, values))
    if isinstance(rule, bool):
        return rule
    if not isinstance(rule, dict):
        return _normalize_active(rule)

    conditions = rule.get("conditions")
    if not isinstance(conditions, list):
        conditions = [rule]
    if not conditions:
        return default

    results = [_evaluate_form_condition(condition, values) for condition in conditions]
    mode = str(rule.get("mode", rule.get("operator", "AND"))).upper()
    return any(results) if mode == "OR" else all(results)


def _is_form_node_visible(node: dict, values: Dict[str, Any]) -> bool:
    if "show_if" in node and not _evaluate_form_rule(node.get("show_if"), values, True):
        return False
    if "hide_if" in node and _evaluate_form_rule(node.get("hide_if"), values, False):
        return False
    return True


def _is_field_widget_visible(fw: dict) -> bool:
    widget = fw.get("input")
    if widget is None:
        return False
    explicit = widget.property("_form_field_visible")
    if explicit is None:
        return True
    return bool(explicit)


def _integer_value(text: str) -> int:
    stripped = str(text or "").strip()
    try:
        return int(stripped)
    except ValueError:
        numeric = float(stripped)
        if numeric.is_integer():
            return int(numeric)
        raise


def _integer_display_value(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _apply_field_visibility(
    field_widgets: Dict[str, dict],
    values: Dict[str, Any],
) -> None:
    for fw in field_widgets.values():
        widget = fw.get("input")
        field_def = fw.get("field_def", {})
        if widget is None or not isinstance(field_def, dict):
            continue
        visible = _is_form_node_visible(field_def, values)
        widget.setProperty("_form_field_visible", visible)
        widget.setVisible(visible)
        spacer = fw.get("after_spacer")
        if isinstance(spacer, QSpacerItem):
            spacer.changeSize(0, 16 if visible else 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        layout = widget.parentWidget().layout() if widget.parentWidget() is not None else None
        if layout is not None:
            layout.invalidate()


def _render_form_nodes(
    parent_layout,
    nodes: List[dict],
    field_widgets: Dict[str, dict],
    errors: Dict[str, str],
    comp_id: str,
    surface_id: str,
    app_instance: Any,
):
    visible_nodes = [node for node in nodes if isinstance(node, dict)]
    for index, node in enumerate(visible_nodes):
        widget, stretch = _build_form_node(
            node=node,
            field_widgets=field_widgets,
            errors=errors,
            comp_id=comp_id,
            surface_id=surface_id,
            app_instance=app_instance,
        )
        if widget is None:
            continue
        parent_layout.addWidget(widget, stretch)
        if index < len(visible_nodes) - 1:
            spacer = QSpacerItem(
                0,
                16,
                QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Fixed,
            )
            parent_layout.addItem(spacer)
            widget.setProperty("_form_after_spacer", spacer)
            for fw in field_widgets.values():
                if fw.get("input") is widget:
                    fw["after_spacer"] = spacer
                    break


def _build_form_node(
    node: dict,
    field_widgets: Dict[str, dict],
    errors: Dict[str, str],
    comp_id: str,
    surface_id: str,
    app_instance: Any,
) -> tuple[Optional[QWidget], int]:
    if _is_layout_node(node):
        direction = str(node.get("type", "column")).lower()
        container = QWidget()
        child_layout = (
            QHBoxLayout(container) if direction == "row" else QVBoxLayout(container)
        )
        child_layout.setContentsMargins(0, 0, 0, 0)
        child_layout.setSpacing(int(node.get("spacing", 16)))

        children = node.get("children") or node.get("items") or []
        if not isinstance(children, list):
            children = []

        built_children = [child for child in children if isinstance(child, dict)]
        for index, child in enumerate(built_children):
            child_widget, child_stretch = _build_form_node(
                node=child,
                field_widgets=field_widgets,
                errors=errors,
                comp_id=comp_id,
                surface_id=surface_id,
                app_instance=app_instance,
            )
            if child_widget is None:
                continue
            if direction == "row":
                child_layout.addWidget(
                    child_widget,
                    child_stretch,
                    Qt.AlignmentFlag.AlignTop,
                )
            else:
                child_layout.addWidget(child_widget, child_stretch)
            if direction == "column" and index < len(built_children) - 1:
                child_layout.addSpacing(8)

        if direction == "row":
            child_layout.addStretch(0)

        stretch = int(node.get("stretch", node.get("span", 0)) or 0)
        return container, max(0, stretch)

    stretch = int(node.get("stretch", node.get("span", 0)) or 0)
    return _build_field_widget(
        field=node,
        field_widgets=field_widgets,
        errors=errors,
        comp_id=comp_id,
        surface_id=surface_id,
        app_instance=app_instance,
    ), max(0, stretch)


def _build_field_widget(
    field: dict,
    field_widgets: Dict[str, dict],
    errors: Dict[str, str],
    comp_id: str,
    surface_id: str,
    app_instance: Any,
) -> Optional[QWidget]:
    name = field.get("name", "")
    if not name:
        return None

    ftype = str(field.get("type", "text")).lower()
    has_error = name in errors
    renderer: Optional[BaseRenderer] = None
    rendered_widget: Optional[QWidget] = None
    input_comp_id = f"{comp_id}_{name}"
    renderer_props: Dict[str, Any] = {"id": input_comp_id}

    if ftype in {"text", "email", "password", "number", "integer", "int", "float", "decimal"}:
        renderer = TextFieldRenderer()
        renderer_props.update(
            {
                "label": field.get("label", name),
                "value": _integer_display_value(field.get("value", ""))
                if ftype in {"integer", "int"}
                else field.get("value", ""),
                "placeholder": field.get("placeholder", ""),
                "password": ftype == "password",
                "input_type": ftype,
            }
        )
        for key in ("min", "max", "decimals"):
            if key in field:
                renderer_props[key] = field.get(key)
    elif ftype == "textarea":
        renderer = TextAreaRenderer()
        renderer_props.update(
            {
                "label": field.get("label", name),
                "value": field.get("value", ""),
                "placeholder": field.get("placeholder", ""),
                "rows": field.get("rows", 3),
                "auto_resize": field.get("auto_resize", True),
            }
        )
    elif ftype in {"checkbox", "check"}:
        renderer = CheckboxRenderer()
        renderer_props.update(
            {
                "label": field.get("label", name),
                "checked": bool(field.get("value", False)),
            }
        )
    elif ftype in {"radio", "radio_group"}:
        renderer = RadioGroupRenderer()
        renderer_props.update(
            {
                "label": field.get("label", name),
                "value": field.get("value", ""),
                "options": field.get("options", []),
            }
        )
    elif ftype == "select":
        renderer = SelectRenderer()
        renderer_props.update(
            {
                "label": field.get("label", name),
                "value": field.get("value", [] if field.get("multiple") else ""),
                "options": field.get("options", []),
                "placeholder": field.get("placeholder", "Select an option"),
                "multiple": bool(field.get("multiple", False)),
            }
        )
    elif ftype in {"file", "attachment"}:
        renderer = AttachmentRenderer()
        raw_value = field.get("value", [])
        normalized_value = raw_value if isinstance(raw_value, list) else []
        renderer_props.update(
            {
                "label": field.get("label", name),
                "value": normalized_value,
                "accept": field.get("accept", ""),
                "multiple": bool(field.get("multiple", False)),
            }
        )
    elif ftype == "audio_recorder":
        renderer = AudioRecorderRenderer()
        raw_value = field.get("value", [])
        normalized_value = raw_value if isinstance(raw_value, list) else []
        renderer_props.update(
            {
                "label": field.get("label", name),
                "value": normalized_value,
                "accept": field.get("accept", "audio/*"),
                "multiple": False,
            }
        )
    elif ftype in {"tags", "tags_input"}:
        renderer = TagsInputRenderer()
        raw_value = field.get("value", [])
        normalized_value = raw_value if isinstance(raw_value, list) else []
        renderer_props.update(
            {
                "label": field.get("label", name),
                "value": normalized_value,
                "placeholder": field.get("placeholder", ""),
                "add_label": field.get("add_label", "Add"),
                "item_schema": field.get("item_schema"),
            }
        )
    elif ftype == "editable_list":
        renderer = EditableListRenderer()
        raw_value = field.get("value", [])
        normalized_value = raw_value if isinstance(raw_value, list) else []
        renderer_props.update(
            {
                "item_label": field.get("label", name),
                "value": normalized_value,
                "placeholder": field.get("placeholder", ""),
                "add_label": field.get("add_label", "Add"),
                "remove_label": field.get("remove_label", "Remove"),
                "submit_label": field.get("submit_label", "Save"),
                "item_schema": field.get("item_schema"),
            }
        )
    elif ftype in {"date", "datetime", "date_time"}:
        renderer = DatePickerRenderer()
        default_format = (
            "yyyy-MM-dd HH:mm" if ftype in {"datetime", "date_time"} else "yyyy-MM-dd"
        )
        renderer_props.update(
            {
                "label": field.get("label", name),
                "value": field.get("value", ""),
                "format": field.get("format", default_format),
                "min_date": field.get("min_date", ""),
                "max_date": field.get("max_date", ""),
            }
        )
    elif ftype in {"toggle", "switch"}:
        renderer = ToggleRenderer()
        renderer_props.update(
            {
                "label": field.get("label", name),
                "checked": bool(field.get("value", False)),
            }
        )

    if renderer is None:
        renderer = TextFieldRenderer()
        renderer_props.update(
            {
                "label": field.get("label", name),
                "value": field.get("value", ""),
                "placeholder": field.get("placeholder", ""),
            }
        )

    if has_error:
        renderer_props["error"] = errors[name]

    rendered_widget = renderer.render(
        renderer_props,
        surface_id,
        app_instance,
        input_comp_id,
    )
    if rendered_widget is None:
        return None

    field_widgets[name] = {
        "input": rendered_widget,
        "renderer": renderer,
        "field_def": field,
    }
    return rendered_widget


def _collect_values(
    field_widgets: Dict[str, dict],
    *,
    include_hidden: bool = False,
) -> Dict[str, Any]:
    values: Dict[str, Any] = {}

    for name, fw in field_widgets.items():
        if not include_hidden and not _is_field_widget_visible(fw):
            continue
        w = fw.get("input")
        field_def = fw.get("field_def", {})
        ftype = str(field_def.get("type", "text")).lower()

        # ── Get value ────────────────────────────────────────
        val: Any = ""
        if w is None:
            val = ""
        elif ftype in ("text", "password", "email", "number", "integer", "int", "float", "decimal"):
            line_edit = w.findChild(QLineEdit)
            text = (
                line_edit.text()
                if line_edit is not None
                else str(w.property("value") or "")
            )
            if ftype in {"integer", "int"}:
                val = "" if str(text or "").strip() == "" else _integer_value(text)
            elif ftype in {"number", "float", "decimal"}:
                val = "" if str(text or "").strip() == "" else float(text)
            else:
                val = text
        elif ftype == "textarea":
            text_edit = w.findChild(QTextEdit)
            val = (
                text_edit.toPlainText()
                if text_edit is not None
                else str(w.property("value") or "")
            )
        elif ftype in ("checkbox", "check", "toggle", "switch"):
            check = w.findChild(QAbstractButton)
            if check is not None:
                val = check.isChecked()
            else:
                raw_bool = w.property("value")
                if raw_bool is None:
                    raw_bool = w.property("checked")
                val = bool(raw_bool)
        elif ftype in (
            "radio",
            "radio_group",
            "date",
            "datetime",
            "date_time",
            "file",
            "attachment",
            "audio_recorder",
        ):
            val = w.property("value")
            if val is None:
                val = ""
        elif ftype == "select":
            val = w.property("value")
            if field_def.get("multiple"):
                if not isinstance(val, list):
                    val = []
            elif val is None:
                val = ""
        elif ftype in ("tags", "tags_input"):
            val = w.property("value")
            if not isinstance(val, list):
                val = []
        elif ftype == "editable_list":
            val = w.property("value")
            if not isinstance(val, list):
                val = []
        else:
            val = w.property("value")
            if val is None:
                line_edit = w.findChild(QLineEdit)
                val = line_edit.text() if line_edit is not None else ""

        values[name] = val

    return values


def _apply_validation(
    field_widgets: Dict[str, dict],
    values: Dict[str, Any],
    target_fields: Optional[set[str]] = None,
) -> bool:
    """Validate fields and update UI; return True if any validated field has errors."""
    has_errors = False
    for name, fw in field_widgets.items():
        if target_fields is not None and name not in target_fields:
            continue
        if not _is_field_widget_visible(fw):
            continue
        w = fw.get("input")
        renderer = fw.get("renderer")
        field_def = fw.get("field_def", {})
        val = values.get(name)
        ftype = str(field_def.get("type", "text")).lower()
        error_msg = _validate_field(field_def, val, values)
        if error_msg:
            has_errors = True

        if renderer is not None:
            renderer.update_widget_property(w, "error", error_msg)
        else:
            _set_error_border(w, ftype, bool(error_msg))

    return has_errors


def _apply_form_values(field_widgets: Dict[str, dict], values: Any) -> None:
    if not isinstance(values, dict):
        return

    for name, value in values.items():
        fw = field_widgets.get(str(name))
        if not isinstance(fw, dict):
            continue
        widget = fw.get("input")
        renderer = fw.get("renderer")
        field_def = fw.get("field_def", {})
        if widget is None or renderer is None:
            continue

        ftype = str(field_def.get("type", "text")).lower()
        field_def["value"] = value
        if ftype in {"checkbox", "check", "toggle", "switch"}:
            renderer.update_widget_property(widget, "checked", bool(value))
        else:
            renderer.update_widget_property(widget, "value", value)


def _collect_and_validate(field_widgets: Dict[str, dict]) -> tuple:
    """Validate all fields, toggle error UI, return (values, has_errors)."""
    values = _collect_values(field_widgets)
    has_errors = _apply_validation(field_widgets, values)
    return values, has_errors


def _materialize_attachment_values(
    field_widgets: Dict[str, dict],
    values: Dict[str, Any],
    *,
    action_def: Dict[str, Any],
    app_instance: Any,
) -> tuple[Dict[str, Any], bool]:
    resolved = dict(values)
    module_name = _infer_module_name({"action": action_def}, app_instance)
    has_errors = False

    for name, fw in field_widgets.items():
        if not _is_field_widget_visible(fw):
            continue
        field_def = fw.get("field_def", {})
        ftype = str(field_def.get("type", "text")).lower()
        if ftype not in {"file", "attachment", "audio_recorder"}:
            continue
        current = resolved.get(name)
        if not isinstance(current, list) or not current:
            continue
        uploaded = upload_attachment_entries(
            current,
            module_name=module_name,
            ingest=field_def.get("ingest") is not False,
            app_instance=app_instance,
        )
        if uploaded is None:
            has_errors = True
            renderer = fw.get("renderer")
            widget = fw.get("input")
            if renderer is not None:
                renderer.update_widget_property(widget, "error", "Upload failed")
            continue
        resolved[name] = uploaded
        renderer = fw.get("renderer")
        widget = fw.get("input")
        if renderer is not None:
            renderer.update_widget_property(widget, "value", uploaded)

    return resolved, has_errors


def _build_cross_field_dependents(
    field_widgets: Dict[str, dict]
) -> Dict[str, set[str]]:
    """Map `field_name -> fields that depend on it` for cross-field validation rules."""
    dependents: Dict[str, set[str]] = {}
    for name, fw in field_widgets.items():
        field_def = fw.get("field_def", {})
        validations = field_def.get("validations", [])
        if not isinstance(validations, list):
            continue
        for rule in validations:
            if not isinstance(rule, dict):
                continue
            rule_name = str(rule.get("rule", "")).strip().lower()
            if rule_name not in {"equals_field", "same_as"}:
                continue
            other = str(rule.get("field") or rule.get("value") or "").strip()
            if not other:
                continue
            dependents.setdefault(other, set()).add(name)
    return dependents


def _set_error_border(widget: Optional[QWidget], ftype: str, is_error: bool):
    """Toggle the border colour between error‑red and default."""
    if widget is None:
        return
    del ftype
    widget.setProperty("invalid", bool(is_error))
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class FormRenderer(BaseRenderer):
    component_type = "Form"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "model": self.PROPERTY,
            "values": self.PROPERTY,
            "errors": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        model: List[dict] = _merge_initial_values(
            props.get("model", []),
            props.get("values"),
        )
        submit_label: str = props.get("submit_label", "Submit")
        submit_full_width: bool = bool(props.get("submit_full_width", False))
        errors: Dict[str, str] = props.get("errors", {})
        action_def = props.get("action", {})
        params = props.get("params", {})
        action_params = params if isinstance(params, dict) else {}

        # ── Neutral wrapper (no card styling) ────────────────────
        container = QWidget()
        container.setObjectName(comp_id)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Field widgets store ──────────────────────────────────
        field_widgets: Dict[str, dict] = {}
        _render_form_nodes(
            parent_layout=layout,
            nodes=model,
            field_widgets=field_widgets,
            errors=errors,
            comp_id=comp_id,
            surface_id=surface_id,
            app_instance=app_instance,
        )
        container.setProperty("_form_field_widgets", field_widgets)
        _apply_field_visibility(
            field_widgets,
            _collect_values(field_widgets, include_hidden=True),
        )

        # ── Live validation while editing ────────────────────────
        touched_fields: set[str] = set()
        has_submitted = {"value": False}
        cross_field_dependents = _build_cross_field_dependents(field_widgets)

        def _validate_live(changed_name: str) -> None:
            if not changed_name:
                return
            current_values = _collect_values(field_widgets, include_hidden=True)
            _apply_field_visibility(field_widgets, current_values)
            if not has_submitted["value"]:
                return
            touched_fields.add(changed_name)
            for dependent in cross_field_dependents.get(changed_name, set()):
                touched_fields.add(dependent)
            values = _collect_values(field_widgets)
            _apply_validation(field_widgets, values, target_fields=touched_fields)

        for field_name, fw in field_widgets.items():
            widget = fw.get("input")
            field_def = fw.get("field_def", {})
            ftype = str(field_def.get("type", "text")).lower()
            if widget is None:
                continue

            # Attachment emits changes from internal upload/remove handlers.
            setattr(
                widget,
                "_form_on_value_changed",
                (lambda n=field_name: _validate_live(n)),
            )

            if ftype in ("text", "password", "email", "number", "integer", "int", "float", "decimal"):
                line_edit = widget.findChild(QLineEdit)
                if line_edit is not None:
                    line_edit.textChanged.connect(
                        lambda _text, n=field_name: _validate_live(n)
                    )
                continue

            if ftype == "textarea":
                text_edit = widget.findChild(QTextEdit)
                if text_edit is not None:
                    text_edit.textChanged.connect(
                        lambda n=field_name: _validate_live(n)
                    )
                continue

            if ftype in ("checkbox", "check"):
                check = widget.findChild(QCheckBox)
                if check is not None:
                    check.stateChanged.connect(
                        lambda _state, n=field_name: _validate_live(n)
                    )
                continue

            if ftype in ("toggle", "switch"):
                switch_btn = widget.findChild(QAbstractButton)
                if switch_btn is not None:
                    switch_btn.toggled.connect(
                        lambda _checked, n=field_name: _validate_live(n)
                    )
                continue

            if ftype == "select":
                combo = widget.findChild(QComboBox)
                if combo is not None:
                    combo.currentIndexChanged.connect(
                        lambda _idx, n=field_name: _validate_live(n)
                    )
                list_widget = widget.findChild(QListWidget)
                if list_widget is not None:
                    list_widget.itemSelectionChanged.connect(
                        lambda n=field_name: _validate_live(n)
                    )
                continue

            if ftype in ("radio", "radio_group"):
                button_group = widget.property("_button_group")
                if isinstance(button_group, QButtonGroup):
                    button_group.buttonClicked.connect(
                        lambda _button, n=field_name: _validate_live(n)
                    )
                continue

            if ftype in ("date", "datetime", "date_time"):
                date_edit = widget.findChild(QLineEdit)
                if date_edit is not None:
                    date_edit.textChanged.connect(
                        lambda _text, n=field_name: _validate_live(n)
                    )
                    date_edit.editingFinished.connect(
                        lambda n=field_name: _validate_live(n)
                    )
                continue

        # ── Spacing before submit ────────────────────────────────
        layout.addSpacing(12)

        # ── Submit button ────────────────────────────────────────
        submit_btn = QPushButton(submit_label)
        submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        submit_btn.setProperty("ui_role", "form_submit_btn")
        if submit_full_width:
            submit_btn.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        else:
            submit_btn.setSizePolicy(
                QSizePolicy.Policy.Maximum,
                QSizePolicy.Policy.Fixed,
            )
        if action_def and action_def.get("name"):
            action_name = str(action_def.get("name"))
            submit_btn.setProperty("_action_name", action_name)
            submit_btn.setProperty("track_loading", props.get("track_loading"))
            track_loading_names = _normalize_track_loading(
                props.get("track_loading"),
                action_name,
            )
            submit_btn.setProperty("_track_loading_names", track_loading_names)
            action_locks = getattr(app_instance, "_action_locks", None)
            if action_locks is not None:
                action_locks.sync_widget(submit_btn)

        def _on_submit():
            has_submitted["value"] = True
            values, has_errors = _collect_and_validate(field_widgets)
            if has_errors:
                return
            values, has_upload_errors = _materialize_attachment_values(
                field_widgets,
                values,
                action_def=action_def if isinstance(action_def, dict) else {},
                app_instance=app_instance,
            )
            if has_upload_errors:
                return
            if action_def:
                emit_action_spec(
                    app_instance,
                    action_def,
                    {
                        **action_params,
                        **values,
                        f"{comp_id}": {**values},
                        "form_id": comp_id,
                    },
                    surface_id,
                    comp_id,
                )

        submit_btn.clicked.connect(_on_submit)
        layout.addWidget(submit_btn)

        return container

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "values":
            field_widgets = widget.property("_form_field_widgets")
            if isinstance(field_widgets, dict):
                _apply_form_values(field_widgets, value)
                _apply_field_visibility(
                    field_widgets,
                    _collect_values(field_widgets, include_hidden=True),
                )
            return
        super().update_widget_property(widget, prop, value)
