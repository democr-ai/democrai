from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...base import BaseRenderer
from .cell_formatters import apply_transform


def _resolve_dynamic_value(
    value: Any,
    app_instance: Any,
    surface_id: str | None = None,
) -> Any:
    bindings = getattr(app_instance, "bindings", None)
    if bindings is None:
        return value
    if isinstance(value, dict):
        if "literalString" in value:
            return value.get("literalString")
        if value.get("type") in {"store", "action", "literal"} or "path" in value:
            try:
                if hasattr(bindings, "resolve_value_for_surface"):
                    return bindings.resolve_value_for_surface(value, surface_id)
                if hasattr(bindings, "resolve_value"):
                    return bindings.resolve_value(value)
                return value
            except Exception:
                return value
    if isinstance(value, str):
        try:
            if hasattr(bindings, "resolve_value_for_surface"):
                return bindings.resolve_value_for_surface(value, surface_id)
            if hasattr(bindings, "resolve_value"):
                return bindings.resolve_value(value)
            return value
        except Exception:
            return value
    return value


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _format_value(
    value: Any,
    field_def: dict[str, Any],
    *,
    app_instance: Any = None,
    row: dict[str, Any] | None = None,
) -> str:
    if value is None:
        return str(field_def.get("placeholder", "-"))

    col_type = str(field_def.get("type", "str")).lower()
    fmt = field_def.get("format")
    transform = field_def.get("transform")
    if transform:
        return apply_transform(
            value,
            transform,
            app_instance=app_instance,
            row=row,
        )

    if col_type == "bool":
        return "Yes" if bool(value) else "No"
    if col_type == "int":
        try:
            cast = int(value)
            if isinstance(fmt, str) and fmt:
                return format(cast, fmt)
            return str(cast)
        except (TypeError, ValueError):
            return str(value)
    if col_type == "float":
        try:
            cast = float(value)
            if isinstance(fmt, str) and fmt:
                return format(cast, fmt)
            return str(cast)
        except (TypeError, ValueError):
            return str(value)
    if col_type in {"date", "datetime"} and isinstance(fmt, str) and fmt:
        try:
            return datetime.fromisoformat(str(value)).strftime(fmt)
        except (TypeError, ValueError):
            return str(value)

    return str(value)


def _normalize_model(model: list[dict[str, Any]], data: dict[str, Any]) -> list[dict[str, Any]]:
    if model:
        return model
    fallback: list[dict[str, Any]] = []
    for key in data.keys():
        fallback.append({"field": str(key), "label": str(key).replace("_", " ").title()})
    return fallback


def _build_table(
    table: QTableWidget,
    *,
    model: list[dict[str, Any]],
    data: dict[str, Any],
    key_header: str,
    value_header: str,
) -> None:
    table.clear()
    table.setColumnCount(2)
    table.setRowCount(len(model))
    table.setHorizontalHeaderLabels([key_header, value_header])

    h_header = table.horizontalHeader()
    h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().setVisible(False)

    last_row_index = len(model) - 1
    for row_index, field_def in enumerate(model):
        field = str(field_def.get("field", "")).strip()
        if not field:
            continue
        key_text = str(
            field_def.get("label")
            or field_def.get("header")
            or field.replace("_", " ").title()
        )
        value_text = _format_value(
            data.get(field),
            field_def,
            app_instance=getattr(table, "_app_instance", None),
            row=data,
        )

        is_last_row = row_index == last_row_index

        key_label = QLabel(key_text)
        key_label.setProperty("ui_role", "descriptions_key_cell")
        key_label.setProperty("last_row", "true" if is_last_row else "false")
        key_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        key_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        table.setCellWidget(row_index, 0, key_label)

        key_item = QTableWidgetItem("")
        key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)
        table.setItem(row_index, 0, key_item)

        value_label = QLabel(value_text)
        value_label.setProperty("ui_role", "descriptions_value_cell")
        value_label.setProperty("last_row", "true" if is_last_row else "false")
        value_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        value_label.setToolTip(value_text)
        value_label.setWordWrap(True)
        table.setCellWidget(row_index, 1, value_label)

        value_item = QTableWidgetItem("")
        value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
        table.setItem(row_index, 1, value_item)


def _autosize_table_height(table: QTableWidget) -> None:
    table.resizeRowsToContents()
    header_h = table.horizontalHeader().height() if table.horizontalHeader() else 0
    rows_h = sum(table.rowHeight(idx) for idx in range(table.rowCount()))
    frame_h = table.frameWidth() * 2
    extra = 2
    total_h = max(40, header_h + rows_h + frame_h + extra)
    table.setMinimumHeight(total_h)
    table.setMaximumHeight(total_h)


class DescriptionsRenderer(BaseRenderer):
    component_type = "Descriptions"

    def binding_strategies(self) -> dict[str, str]:
        return {
            **super().binding_strategies(),
            "model": self.COMPONENT,
            "data": self.COMPONENT,
            "key_header": self.COMPONENT,
            "value_header": self.COMPONENT,
            "borders": self.COMPONENT,
        }

    def render(
        self,
        props: dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ) -> QWidget:
        model_raw = list(props.get("model", [])) if isinstance(props.get("model", []), list) else []
        data_raw = dict(props.get("data", {})) if isinstance(props.get("data", {}), dict) else {}

        model: list[dict[str, Any]] = []
        for field_def in model_raw:
            if not isinstance(field_def, dict):
                continue
            resolved_field_def = {
                key: _resolve_dynamic_value(val, app_instance, surface_id)
                for key, val in field_def.items()
            }
            model.append(resolved_field_def)

        data = {
            str(key): _resolve_dynamic_value(value, app_instance)
            for key, value in data_raw.items()
        }
        model = _normalize_model(model, data)
        key_header = str(_resolve_dynamic_value(props.get("key_header", "Property"), app_instance))
        value_header = str(_resolve_dynamic_value(props.get("value_header", "Value"), app_instance))
        borders = _coerce_bool(_resolve_dynamic_value(props.get("borders", True), app_instance), True)

        card = QFrame()
        card.setObjectName(comp_id)
        card.setProperty("ui_role", "descriptions_card")
        card.setProperty("borders", "true" if borders else "false")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)

        table = QTableWidget()
        table.setObjectName(f"{comp_id}_table")
        table._app_instance = app_instance  # type: ignore[attr-defined]
        table.setProperty("ui_role", "descriptions_table")
        table.setProperty("borders", "true" if borders else "false")
        table.setShowGrid(borders)
        table.setWordWrap(True)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _build_table(
            table,
            model=model,
            data=data,
            key_header=key_header,
            value_header=value_header,
        )
        _autosize_table_height(table)

        layout.addWidget(table)

        card._desc_table = table  # type: ignore[attr-defined]
        card._desc_model = model  # type: ignore[attr-defined]
        card._desc_data = data  # type: ignore[attr-defined]
        card._desc_key_header = key_header  # type: ignore[attr-defined]
        card._desc_value_header = value_header  # type: ignore[attr-defined]
        card._desc_borders = borders  # type: ignore[attr-defined]
        card._desc_app = app_instance  # type: ignore[attr-defined]
        return card

    def _rebuild_widget(self, widget: QWidget) -> None:
        table = getattr(widget, "_desc_table", None)
        app_instance = getattr(widget, "_desc_app", None)
        if table is None:
            return

        model_raw = getattr(widget, "_desc_model", [])
        data_raw = getattr(widget, "_desc_data", {})

        model: list[dict[str, Any]] = []
        for field_def in model_raw if isinstance(model_raw, list) else []:
            if not isinstance(field_def, dict):
                continue
            resolved_field_def = {
                key: _resolve_dynamic_value(val, app_instance)
                for key, val in field_def.items()
            }
            model.append(resolved_field_def)

        data: dict[str, Any] = {}
        if isinstance(data_raw, dict):
            for key, value in data_raw.items():
                data[str(key)] = _resolve_dynamic_value(value, app_instance)

        model = _normalize_model(model, data)
        key_header = str(
            _resolve_dynamic_value(getattr(widget, "_desc_key_header", "Property"), app_instance)
        )
        value_header = str(
            _resolve_dynamic_value(getattr(widget, "_desc_value_header", "Value"), app_instance)
        )
        borders = _coerce_bool(
            _resolve_dynamic_value(getattr(widget, "_desc_borders", True), app_instance),
            True,
        )

        widget._desc_model = model  # type: ignore[attr-defined]
        widget._desc_data = data  # type: ignore[attr-defined]
        widget._desc_key_header = key_header  # type: ignore[attr-defined]
        widget._desc_value_header = value_header  # type: ignore[attr-defined]
        widget._desc_borders = borders  # type: ignore[attr-defined]

        widget.setProperty("borders", "true" if borders else "false")
        table.setProperty("borders", "true" if borders else "false")
        table.setShowGrid(borders)
        _build_table(
            table,
            model=model,
            data=data,
            key_header=key_header,
            value_header=value_header,
        )
        _autosize_table_height(table)
        table.style().unpolish(table)
        table.style().polish(table)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop in {"model", "data", "key_header", "value_header", "borders"}:
            if prop == "model":
                widget._desc_model = value if isinstance(value, list) else []  # type: ignore[attr-defined]
            elif prop == "data":
                widget._desc_data = value if isinstance(value, dict) else {}  # type: ignore[attr-defined]
            elif prop == "key_header":
                widget._desc_key_header = value  # type: ignore[attr-defined]
            elif prop == "value_header":
                widget._desc_value_header = value  # type: ignore[attr-defined]
            elif prop == "borders":
                widget._desc_borders = _coerce_bool(value, True)  # type: ignore[attr-defined]
            self._rebuild_widget(widget)
            return
        super().update_widget_property(widget, prop, value)
