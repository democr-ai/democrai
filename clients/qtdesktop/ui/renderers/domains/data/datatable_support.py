from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import shiboken6
from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...base import emit_action, emit_action_spec
from ...base_visibility import (
    evaluate_condition,
    evaluate_visibility_rule,
    spec_is_visible,
)
from ...icon import get_icon, normalize_icon_name
from ....theme.tokens import theme_token
from .cell_formatters import apply_transform


def qt_object_alive(obj: Any) -> bool:
    try:
        return obj is not None and shiboken6.isValid(obj)
    except Exception:
        return obj is not None


# ---------------------------------------------------------------------------
# Remote action helpers
# ---------------------------------------------------------------------------

def normalize_action_spec(spec: Any) -> dict[str, Any] | None:
    if isinstance(spec, str) and spec.strip():
        return {"name": spec.strip(), "context": {}}
    if isinstance(spec, dict):
        name = str(spec.get("name") or "").strip()
        if name:
            return {"name": name, "context": dict(spec.get("context", {}) or {})}
    return None


def normalize_sort_state(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    field = str(raw.get("field") or raw.get("sortField") or "").strip()
    if not field:
        return {}
    direction = str(
        raw.get("direction") or raw.get("sortDirection") or "asc"
    ).strip().lower()
    if direction not in {"asc", "desc"}:
        direction = "asc"
    return {"field": field, "direction": direction}


_TABLE_RESERVED_QUERY_KEYS = {"page", "page_size", "sort_field", "sort_direction"}


def get_current_path(app_instance: Any) -> str:
    store = getattr(app_instance, "store", None)
    if store is not None and hasattr(store, "get"):
        try:
            return str(store.get("/current_path", "/", "global") or "/")
        except Exception:
            return "/"
    return "/"


def parse_table_query_state(
    path: str,
    table_id: str,
    *,
    default_page: int,
    default_page_size: int,
    default_filters: dict[str, Any] | None = None,
    default_sort: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parsed = urlparse(str(path or "/"))
    qs = parse_qs(parsed.query, keep_blank_values=False)
    prefix = f"{table_id}["
    filters: dict[str, Any] = {}
    for key, values in qs.items():
        if not key.startswith(prefix) or not key.endswith("]"):
            continue
        inner = key[len(prefix) : -1].strip()
        if not inner or inner in _TABLE_RESERVED_QUERY_KEYS:
            continue
        value = str((values or [""])[-1] or "").strip()
        if value:
            filters[inner] = value

    page_raw = str((qs.get(f"{table_id}[page]") or [default_page])[-1])
    page_size_raw = str((qs.get(f"{table_id}[page_size]") or [default_page_size])[-1])
    sort_field_raw = str((qs.get(f"{table_id}[sort_field]") or [""])[-1] or "").strip()
    sort_direction_raw = str((qs.get(f"{table_id}[sort_direction]") or [""])[-1] or "").strip().lower()

    try:
        page = max(0, int(page_raw or default_page))
    except (TypeError, ValueError):
        page = max(0, int(default_page or 0))
    try:
        page_size = max(1, int(page_size_raw or default_page_size))
    except (TypeError, ValueError):
        page_size = max(1, int(default_page_size or 25))

    fallback_sort = normalize_sort_state(default_sort or {})
    sort_candidate = {
        "field": sort_field_raw or fallback_sort.get("field", ""),
        "direction": sort_direction_raw or fallback_sort.get("direction", "asc"),
    }
    sort_state = normalize_sort_state(sort_candidate) or fallback_sort

    return {
        "page": page,
        "page_size": page_size,
        "filters": filters if filters else dict(default_filters or {}),
        "sort": dict(sort_state or {}),
    }


def path_with_table_query(
    path: str,
    table_id: str,
    *,
    page: int,
    page_size: int,
    filters: dict[str, Any] | None,
    sort: dict[str, Any] | None,
) -> str:
    parsed = urlparse(str(path or "/"))
    qs = parse_qs(parsed.query, keep_blank_values=False)
    prefix = f"{table_id}["
    qs = {k: v for k, v in qs.items() if not k.startswith(prefix)}
    qs[f"{table_id}[page]"] = [str(max(0, int(page or 0)))]
    qs[f"{table_id}[page_size]"] = [str(max(1, int(page_size or 1)))]

    normalized_sort = normalize_sort_state(sort or {})
    if normalized_sort.get("field"):
        qs[f"{table_id}[sort_field]"] = [str(normalized_sort["field"])]
    if normalized_sort.get("direction"):
        qs[f"{table_id}[sort_direction]"] = [str(normalized_sort["direction"])]

    for field, value in dict(filters or {}).items():
        if value is None or value == "":
            continue
        qs[f"{table_id}[{field}]"] = [str(value)]

    new_query = urlencode({k: v[0] for k, v in qs.items()})
    return urlunparse(parsed._replace(query=new_query))


def navigate_table_query(
    card: Any,
    *,
    page: int | None = None,
    page_size: int | None = None,
    filters: dict[str, Any] | None = None,
    sort: dict[str, Any] | None = None,
) -> bool:
    app = getattr(card, "_dt_app", None)
    if app is None:
        return False
    table_id = str(getattr(card, "_dt_comp_id", "") or "")
    if not table_id:
        return False
    current_path = get_current_path(app)
    next_page = max(0, int(page if page is not None else getattr(card, "_dt_page", 0) or 0))
    next_page_size = max(1, int(page_size if page_size is not None else getattr(card, "_dt_page_size", 25) or 25))
    next_filters = dict(filters if filters is not None else getattr(card, "_dt_filters", {}) or {})
    next_sort = normalize_sort_state(sort if sort is not None else getattr(card, "_dt_sort", {}))
    next_path = path_with_table_query(
        current_path,
        table_id,
        page=next_page,
        page_size=next_page_size,
        filters=next_filters,
        sort=next_sort,
    )
    if next_path == current_path:
        return False
    card._dt_page = next_page  # type: ignore[attr-defined]
    card._dt_page_size = next_page_size  # type: ignore[attr-defined]
    card._dt_filters = next_filters  # type: ignore[attr-defined]
    card._dt_sort = dict(next_sort)  # type: ignore[attr-defined]
    emit_action(
        app,
        "navigate",
        {"path": next_path, "render": False},
        getattr(card, "_dt_surface_id", "main"),
        getattr(card, "_dt_comp_id", ""),
    )
    return True


def query_state_key(path: str, table_id: str) -> str:
    parsed = urlparse(str(path or "/"))
    qs = parse_qs(parsed.query, keep_blank_values=False)
    prefix = f"{table_id}["
    relevant = {k: (v[-1] if v else "") for k, v in qs.items() if k.startswith(prefix)}
    return urlencode(relevant)


def build_datatable_action_payload(
    card: Any,
    *,
    page: int | None = None,
    page_size: int | None = None,
    filters: dict[str, Any] | None = None,
    sort: dict[str, Any] | None = None,
    auto_refresh: bool = False,
) -> dict[str, Any]:
    table_id = str(getattr(card, "_dt_comp_id", "") or "")
    payload = {
        "page": max(0, int(page if page is not None else getattr(card, "_dt_page", 0) or 0)),
        "pageSize": max(
            1,
            int(
                page_size
                if page_size is not None
                else getattr(card, "_dt_page_size", 25) or 25
            ),
        ),
        "filters": dict(
            filters if filters is not None else getattr(card, "_dt_filters", {}) or {}
        ),
        "tableId": table_id,
    }
    sort_state = normalize_sort_state(
        sort if sort is not None else getattr(card, "_dt_sort", {})
    )
    if sort_state:
        payload["sort"] = dict(sort_state)
        payload["sortField"] = sort_state["field"]
        payload["sortDirection"] = sort_state["direction"]
    if auto_refresh:
        payload["autoRefresh"] = True
    return payload


def _emit_bound_action(
    card: Any,
    action_spec: dict[str, Any] | None,
    payload: dict[str, Any],
) -> bool:
    if not action_spec:
        return False
    app_instance = getattr(card, "_dt_app", None)
    surface_id = getattr(card, "_dt_surface_id", "main")
    comp_id = getattr(card, "_dt_comp_id", "")
    if app_instance is None:
        return False
    emit_action(
        app_instance,
        action_spec["name"],
        {**action_spec.get("context", {}), **payload},
        surface_id,
        comp_id,
    )
    return True


def column_is_remote_sortable(col_def: dict[str, Any], remote_action: dict[str, Any] | None) -> bool:
    if not remote_action:
        return False
    sortable = col_def.get("sortable")
    return sortable is not False and bool(col_def.get("field"))


def header_label_with_sort(
    col_def: dict[str, Any],
    sort_state: dict[str, str] | None,
    *,
    remote_action: dict[str, Any] | None,
) -> str:
    label = str(col_def.get("header") or col_def.get("field") or "")
    if not column_is_remote_sortable(col_def, remote_action):
        return label
    field = str(col_def.get("field") or "").strip()
    if not field:
        return label
    normalized = normalize_sort_state(sort_state or {})
    if normalized.get("field") != field:
        return f"{label}  <->"
    direction = normalized.get("direction", "asc")
    return f"{label}  {'↑' if direction == 'asc' else '↓'}"


def refresh_remote_sort_indicators(card: Any) -> None:
    if not qt_object_alive(card):
        return

    model = getattr(card, "_dt_model", []) or []
    remote_action = getattr(card, "_dt_remote_service", None)
    sort_state = normalize_sort_state(getattr(card, "_dt_sort", {}))

    table = getattr(card, "_dt_table", None)
    col_offset = getattr(card, "_dt_col_offset", 0)
    if qt_object_alive(table):
        for index, col_def in enumerate(model):
            real_col = index + col_offset
            item = table.horizontalHeaderItem(real_col)
            if item is not None:
                item.setText(
                    header_label_with_sort(
                        col_def,
                        sort_state,
                        remote_action=remote_action,
                    )
                )

    buttons = getattr(card, "_dt_sort_buttons", {}) or {}
    if isinstance(buttons, dict):
        for field, button in buttons.items():
            if not qt_object_alive(button):
                continue
            col_def = next(
                (
                    item
                    for item in model
                    if str(item.get("field") or "").strip() == str(field).strip()
                ),
                None,
            )
            if col_def is None:
                continue
            button.setText(
                header_label_with_sort(
                    col_def,
                    sort_state,
                    remote_action=remote_action,
                )
            )


def cycle_sort_state(current: dict[str, Any] | None, field: str) -> dict[str, str]:
    normalized = normalize_sort_state(current or {})
    if normalized.get("field") != field:
        return {"field": field, "direction": "asc"}
    if normalized.get("direction") == "asc":
        return {"field": field, "direction": "desc"}
    return {}


# ---------------------------------------------------------------------------
# Evaluator helpers
# ---------------------------------------------------------------------------

def _eval_rule(rule: Any, app_instance: Any, row: dict[str, Any] | None, *, default: bool = True) -> bool:
    """Evaluate a selectable/editable bool, single condition, or visibility rule with row as item."""
    if rule is None:
        return default
    if isinstance(rule, bool):
        return rule
    if not isinstance(rule, dict):
        return bool(rule)
    if "conditions" in rule or "mode" in rule or "operator" in rule:
        return evaluate_visibility_rule(rule, app_instance, row, default=default)
    if "left" in rule or "op" in rule or "value1" in rule:
        return evaluate_condition(rule, app_instance, row)
    return default


def _is_visible(spec: dict[str, Any], app_instance: Any, row: dict[str, Any] | None) -> bool:
    """Check standard action visibility contract for an action/column spec."""
    return spec_is_visible(spec, app_instance, row)


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------

def cast_value(text: str, col_type: str) -> Any:
    try:
        if col_type == "int":
            return int(text)
        if col_type == "float":
            return float(text)
        if col_type == "bool":
            return text.lower() in ("true", "1", "yes", "sì")
    except (ValueError, TypeError):
        pass
    return text


def resolve_row_index(rows: list[dict[str, Any]], payload: Any) -> int | None:
    if isinstance(payload, int):
        return payload if 0 <= payload < len(rows) else None
    if isinstance(payload, dict):
        if isinstance(payload.get("index"), int):
            index = int(payload["index"])
            return index if 0 <= index < len(rows) else None
        target_id = payload.get("id")
        if target_id is not None:
            for index, row in enumerate(rows):
                if isinstance(row, dict) and row.get("id") == target_id:
                    return index
    return None


def get_row_data(table: QTableWidget, row: int, model: list[dict[str, Any]], col_offset: int) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for col_idx, col_def in enumerate(model):
        real_col = col_idx + col_offset
        field = col_def.get("field", "")
        widget = table.cellWidget(row, real_col)
        if isinstance(widget, QComboBox):
            data[field] = cast_value(widget.currentText(), col_def.get("type", "str"))
            continue
        item = table.item(row, real_col)
        if item:
            data[field] = cast_value(item.text(), col_def.get("type", "str"))
    return data


# ---------------------------------------------------------------------------
# Column layout
# Column 0: row-action menu button (if row_actions)
# Column 0 or 1: checkbox (if selectable)
# Following cols: model fields
# Last col (legacy only): delete button (if on_row_delete and not row_actions)
# ---------------------------------------------------------------------------

ACTION_COL_WIDTH = 40
CHECKBOX_COL_WIDTH = 44


def compute_layout(
    *,
    selectable: bool,
    model: list,
    row_actions: list | None,
    on_row_delete: dict | None,
) -> tuple[int, int | None, int | None, int]:
    """Returns (col_offset, action_col, legacy_del_col, total_cols).

    action_col   : index of the 3-dot button column  (None if not present)
    legacy_del_col: index of the ✕ button column     (None if not present)
    col_offset   : where model fields start
    """
    idx = 0
    action_col: int | None = None
    legacy_del_col: int | None = None

    if row_actions:
        action_col = idx
        idx += 1

    if selectable:
        idx += 1   # checkbox col follows action col

    col_offset = idx
    idx += len(model)

    if on_row_delete and not row_actions:
        legacy_del_col = idx
        idx += 1

    return col_offset, action_col, legacy_del_col, idx


# ---------------------------------------------------------------------------
# Table configuration
# ---------------------------------------------------------------------------

def configure_table(
    *,
    table: QTableWidget,
    model: list[dict[str, Any]],
    on_row_delete: dict[str, Any] | None,
    show_row_numbers: bool,
    selectable: bool = False,
    row_actions: list[dict[str, Any]] | None = None,
    remote_action: dict[str, Any] | None = None,
    sort_state: dict[str, Any] | None = None,
) -> tuple[int, int | None, int | None]:
    """Configure the QTableWidget. Returns (col_offset, action_col, legacy_del_col)."""
    col_offset, action_col, legacy_del_col, total_cols = compute_layout(
        selectable=selectable, model=model,
        row_actions=row_actions, on_row_delete=on_row_delete,
    )
    checkbox_col: int | None = action_col + 1 if (selectable and action_col is not None) else (0 if selectable else None)

    table.setColumnCount(total_cols)
    table.setAutoFillBackground(True)
    table.setProperty("ui_role", "datatable_table")
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.verticalHeader().setVisible(show_row_numbers)
    table.verticalHeader().setFixedWidth(36)   # consistent width for header/filter alignment
    table.setShowGrid(True)
    table.setWordWrap(False)
    table.verticalHeader().setMinimumSectionSize(28)
    table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    viewport = table.viewport()
    if viewport is not None and hasattr(viewport, "setAutoFillBackground"):
        viewport.setAutoFillBackground(True)

    # ---- Build headers ----
    headers: list[str] = []
    if action_col is not None:
        headers.append("")
    if checkbox_col is not None:
        headers.append("")
    headers += [
        header_label_with_sort(
            col,
            sort_state,
            remote_action=remote_action,
        )
        for col in model
    ]
    if legacy_del_col is not None:
        headers.append("")
    table.setHorizontalHeaderLabels(headers)

    h_header = table.horizontalHeader()
    has_last_fixed = legacy_del_col is not None
    h_header.setStretchLastSection(not has_last_fixed)
    h_header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    if action_col is not None:
        table.setColumnWidth(action_col, ACTION_COL_WIDTH)
        h_header.setSectionResizeMode(action_col, QHeaderView.ResizeMode.Fixed)

    if checkbox_col is not None:
        table.setColumnWidth(checkbox_col, CHECKBOX_COL_WIDTH)
        h_header.setSectionResizeMode(checkbox_col, QHeaderView.ResizeMode.Fixed)

    for i, col_def in enumerate(model):
        real_col = i + col_offset
        width = col_def.get("width")
        if width:
            table.setColumnWidth(real_col, int(width))
            h_header.setSectionResizeMode(real_col, QHeaderView.ResizeMode.Fixed)
        else:
            h_header.setSectionResizeMode(real_col, QHeaderView.ResizeMode.Stretch)

    if legacy_del_col is not None:
        table.setColumnWidth(legacy_del_col, 60)
        h_header.setSectionResizeMode(legacy_del_col, QHeaderView.ResizeMode.Fixed)

    return col_offset, action_col, legacy_del_col


# ---------------------------------------------------------------------------
# Row population
# ---------------------------------------------------------------------------

def populate_row(
    *,
    table: QTableWidget,
    row_idx: int,
    row_data: dict[str, Any],
    model: list[dict[str, Any]],
    on_row_delete: dict[str, Any] | None,
    surface_id: str,
    comp_id: str,
    app_instance: Any,
    selectable: bool = False,
    row_actions: list[dict[str, Any]] | None = None,
    col_offset: int = 0,
    action_col: int | None = None,
    legacy_del_col: int | None = None,
    card: Any = None,
) -> None:
    checkbox_col: int | None = None
    if selectable:
        checkbox_col = (action_col + 1) if action_col is not None else 0

    # --- 3-dot action button ---
    if action_col is not None and row_actions:
        _add_row_action_button(
            table=table, row_idx=row_idx, action_col=action_col,
            row_data=row_data, row_actions=row_actions,
            app_instance=app_instance, surface_id=surface_id, comp_id=comp_id,
        )

    # --- Checkbox ---
    if checkbox_col is not None:
        cb = QCheckBox()
        cb.setProperty("ui_role", "datatable_row_checkbox")
        row_selectable = _eval_rule(row_data.get("selectable", True), app_instance, row_data)
        cb.setEnabled(row_selectable)
        row_id = row_data.get("id")

        def _on_check(state: int, _rid=row_id, _card=card) -> None:
            if _card is None:
                return
            selected: set = getattr(_card, "_dt_selected_ids", set())
            if state == Qt.CheckState.Checked.value or state == 2:
                selected.add(_rid)
            else:
                selected.discard(_rid)
            _card._dt_selected_ids = selected  # type: ignore[attr-defined]
            _update_selection_bar(_card)

        cb.stateChanged.connect(_on_check)
        cell_widget = QWidget()
        cell_layout = QHBoxLayout(cell_widget)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cell_layout.addWidget(cb)
        table.setCellWidget(row_idx, checkbox_col, cell_widget)

    # --- Model columns ---
    for col_idx, col_def in enumerate(model):
        real_col = col_idx + col_offset
        field      = col_def.get("field", "")
        raw_value  = row_data.get(field, "")
        display_text = apply_transform(
            raw_value,
            col_def.get("transform"),
            row=row_data,
            app_instance=app_instance,
        )
        editable   = _eval_rule(col_def.get("editable", False), app_instance, row_data, default=False)
        col_type   = col_def.get("type", "str")

        if col_type == "enum" and editable:
            combo = QComboBox()
            combo.setFixedHeight(28)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.setProperty("ui_role", "datatable_cell_combo")
            options_field = str(col_def.get("options_field") or "").strip()
            options = (
                row_data.get(options_field)
                if options_field and isinstance(row_data.get(options_field), list)
                else col_def.get("options", [])
            )
            for opt in options:
                if isinstance(opt, dict):
                    value = str(opt.get("value") or "")
                    label = str(opt.get("label") or value)
                else:
                    value = str(opt)
                    label = value
                combo.addItem(label, value)
            idx = combo.findData(str(raw_value))
            if idx >= 0:
                combo.setCurrentIndex(idx)
            table.setCellWidget(row_idx, real_col, combo)

            if card is not None:
                _row_id = row_data.get("id")

                def _on_combo_changed(
                    _,
                    _combo=combo,
                    _field=field,
                    _row_idx=row_idx,
                    _row_id=_row_id,
                    _card=card,
                ) -> None:
                    new_val = str(_combo.currentData() or "")
                    _update_card_rows(_card, _row_idx, _field, new_val)
                    props = getattr(_card, "_dt_props", {})
                    on_ce = props.get("on_cell_edit")
                    if on_ce:
                        _app = getattr(_card, "_dt_app", None)
                        _sid = getattr(_card, "_dt_surface_id", "main")
                        _cid = getattr(_card, "_dt_comp_id", "")
                        if _app:
                            emit_action(
                                _app, on_ce["name"],
                                {**on_ce.get("context", {}),
                                 "rowId": _row_id,
                                 "rowIndex": _row_idx,
                                 "field": _field,
                                 "value": new_val,
                                 "tableId": _cid},
                                _sid, _cid,
                            )
                combo.currentIndexChanged.connect(_on_combo_changed)

            continue

        if col_type == "bool":
            item = QTableWidgetItem()
            item.setCheckState(Qt.CheckState.Checked if raw_value else Qt.CheckState.Unchecked)
            if not editable:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            table.setItem(row_idx, real_col, item)
            continue

        item = QTableWidgetItem(display_text)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setForeground(QColor(theme_token("text.muted", app_instance=app_instance)))
        else:
            item.setForeground(QColor(theme_token("text.primary", app_instance=app_instance)))
        table.setItem(row_idx, real_col, item)

    # --- Legacy delete button ---
    if legacy_del_col is not None and on_row_delete:
        row_data_copy = dict(row_data)
        ri = row_idx
        del_btn = QPushButton("✕")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setProperty("ui_role", "datatable_delete_btn")
        del_btn.clicked.connect(
            lambda _=False, rd=row_data_copy, r=ri: emit_action_spec(
                app_instance,
                on_row_delete,
                {"row_index": r, "row_data": rd},
                surface_id,
                comp_id,
            )
        )
        table.setCellWidget(row_idx, legacy_del_col, del_btn)


def _add_row_action_button(
    *,
    table: QTableWidget,
    row_idx: int,
    action_col: int,
    row_data: dict[str, Any],
    row_actions: list[dict[str, Any]],
    app_instance: Any,
    surface_id: str,
    comp_id: str,
) -> None:
    btn = QToolButton()
    icon_default = theme_token("icon.default", app_instance=app_instance)
    btn.setIcon(get_icon("ric.more-2-fill", icon_default, 16))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setAutoRaise(True)
    btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    btn.setProperty("ui_role", "datatable_action_btn")

    menu = QMenu(btn)
    rd = dict(row_data)

    for ra in row_actions:
        if not _is_visible(ra, app_instance, rd):
            continue
        label   = str(ra.get("label") or "")
        icon_s  = str(ra.get("icon") or "").strip()
        action  = ra.get("action") or {}
        variant = ra.get("variant", "")

        act = QAction(label, menu)
        if icon_s:
            act.setIcon(get_icon(normalize_icon_name(icon_s), icon_default, 14))
        if variant == "danger":
            act.setProperty("ui_role", "datatable_menu_danger")

        act_copy = dict(action) if isinstance(action, dict) else action
        act.triggered.connect(
            lambda _=False, _a=act_copy, _d=rd, _r=row_idx: _emit_row_action(
                app_instance,
                _a,
                _d,
                _r,
                surface_id,
                comp_id,
            )
        )
        menu.addAction(act)

    btn.setMenu(menu)
    table.setCellWidget(row_idx, action_col, btn)


def _emit_row_action(
    app_instance: Any,
    action_spec: Any,
    row_data: dict[str, Any],
    row_index: int,
    surface_id: str,
    comp_id: str,
) -> None:
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

    item = dict(row_data)
    renderer = getattr(app_instance, "renderer", None)
    resolve_bindings = getattr(renderer, "resolve_bindings", None)
    if callable(resolve_bindings):
        resolved_context = resolve_bindings(context, item=item, property_name="context")
    else:
        resolved_context = dict(context)
    if not isinstance(resolved_context, dict):
        resolved_context = {}
    resolved_context.update({"item": item, "item_index": row_index})

    emit_action_spec(
        app_instance,
        dispatch_spec,
        resolved_context,
        surface_id,
        comp_id,
    )


# ---------------------------------------------------------------------------
# Client-side (in-memory) filtering helpers
# ---------------------------------------------------------------------------

def _apply_filters_local(rows: list[dict[str, Any]], filters: dict) -> list[dict[str, Any]]:
    if not filters:
        return rows
    result = []
    for row in rows:
        match = True
        for field, value in filters.items():
            if value is None or value == "":
                continue
            cell = row.get(field)
            if isinstance(value, bool):
                if bool(cell) != value:
                    match = False
                    break
            else:
                if str(value).lower() not in str(cell).lower():
                    match = False
                    break
        if match:
            result.append(row)
    return result


def _update_card_rows(card: Any, row_idx: int, field: str, value: Any) -> None:
    """Mutate _dt_rows[row_idx] and the matching entry in _dt_all_rows in-place."""
    dt_rows = getattr(card, "_dt_rows", [])
    if row_idx < 0 or row_idx >= len(dt_rows):
        return
    row = dt_rows[row_idx]
    row_id = row.get("id")
    row[field] = value

    for r in getattr(card, "_dt_all_rows", []):
        if r.get("id") == row_id or (row_id is None and r is row):
            r[field] = value
            break


def reset_table_rows(card: Any, rows: list[dict[str, Any]]) -> None:
    """Replace the visible rows in a DataTable card (used for client-side filtering)."""
    table        = getattr(card, "_dt_table", None)
    model        = getattr(card, "_dt_model", None)
    props        = getattr(card, "_dt_props", {})
    col_offset   = getattr(card, "_dt_col_offset", 0)
    action_col   = getattr(card, "_dt_action_col", None)
    legacy_del_col = getattr(card, "_dt_legacy_del_col", None)
    on_row_delete = props.get("on_row_delete")
    row_actions   = props.get("row_actions") or None
    selectable    = bool(props.get("selectable", False))
    surface_id    = getattr(card, "_dt_surface_id", "main")
    comp_id       = getattr(card, "_dt_comp_id", "")
    app_instance  = getattr(card, "_dt_app", None)
    if table is None or model is None or app_instance is None:
        return
    table.blockSignals(True)
    table.setRowCount(0)
    table.setRowCount(len(rows))
    for row_idx, row_data in enumerate(rows):
        populate_row(
            table=table, row_idx=row_idx, row_data=row_data,
            model=model, on_row_delete=on_row_delete,
            surface_id=surface_id, comp_id=comp_id, app_instance=app_instance,
            selectable=selectable, row_actions=row_actions,
            col_offset=col_offset, action_col=action_col,
            legacy_del_col=legacy_del_col, card=card,
        )
    table.blockSignals(False)
    card._dt_rows = rows  # type: ignore[attr-defined]
    if hasattr(card, "_dt_selected_ids"):
        card._dt_selected_ids = set()  # type: ignore[attr-defined]
        _update_selection_bar(card)
    if table.viewport() is not None:
        table.viewport().update()
    table.update()


# ---------------------------------------------------------------------------
# Filter bar (synchronized with table column widths)
# ---------------------------------------------------------------------------

def build_filter_bar(
    *,
    model: list[dict[str, Any]],
    action_col: int | None,
    selectable: bool,
    on_filter_change: dict[str, Any] | None,
    app_instance: Any,
    surface_id: str,
    comp_id: str,
    card: Any,
    row_numbers_width: int = 0,
) -> QWidget | None:
    filterable = [col for col in model if col.get("filterable")]
    if not filterable:
        return None

    bar = QWidget()
    bar.setProperty("ui_role", "datatable_filter_bar")
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(0, 2, 0, 2)
    layout.setSpacing(0)

    if row_numbers_width > 0:
        spacer_rn = QWidget()
        spacer_rn.setFixedWidth(row_numbers_width)
        layout.addWidget(spacer_rn)

    # Placeholder for action column
    if action_col is not None:
        spacer = QWidget()
        spacer.setFixedWidth(ACTION_COL_WIDTH)
        layout.addWidget(spacer)

    # Placeholder for checkbox column
    if selectable:
        spacer2 = QWidget()
        spacer2.setFixedWidth(CHECKBOX_COL_WIDTH)
        layout.addWidget(spacer2)

    filter_widgets: list[tuple[str, QWidget]] = []

    for col in model:
        field       = col.get("field", "")
        filter_type = col.get("filter_type", "text")
        options     = col.get("options", [])
        width       = col.get("width")

        container = QWidget()
        c_layout  = QHBoxLayout(container)
        c_layout.setContentsMargins(2, 0, 2, 0)
        c_layout.setSpacing(0)

        if not col.get("filterable"):
            # empty placeholder — stretches like the column
            if width:
                container.setFixedWidth(int(width))
            else:
                c_layout.addStretch(1)
            layout.addWidget(container, 0 if width else 1)
            continue

        if filter_type in ("select",) and options:
            widget: QWidget = QComboBox()
            widget.setProperty("ui_role", "datatable_filter_select")
            widget.setFixedHeight(24)
            combo: QComboBox = widget  # type: ignore[assignment]
            combo.addItem("All", None)
            for opt in options:
                combo.addItem(str(opt), opt)

            def _on_select(idx: int, _f=field, _c=combo, _card=card) -> None:
                val = _c.itemData(idx)
                filters = dict(getattr(_card, "_dt_filters", {}))
                if val is None:
                    filters.pop(_f, None)
                else:
                    filters[_f] = val
                _card._dt_filters = filters  # type: ignore[attr-defined]
                if getattr(_card, "_dt_remote_service", None):
                    navigate_table_query(_card, page=0, filters=filters)
                elif on_filter_change:
                    _emit_bound_action(
                        _card,
                        on_filter_change,
                        build_datatable_action_payload(_card, page=0, filters=filters),
                    )
                else:
                    all_rows = list(getattr(_card, "_dt_all_rows", getattr(_card, "_dt_rows", [])))
                    reset_table_rows(_card, _apply_filters_local(all_rows, filters))

            combo.currentIndexChanged.connect(_on_select)

        elif filter_type == "boolean":
            widget = QComboBox()
            widget.setProperty("ui_role", "datatable_filter_select")
            widget.setFixedHeight(24)
            combo = widget  # type: ignore[assignment]
            combo.addItem("All",  None)
            combo.addItem("Yes",  True)
            combo.addItem("No",   False)

            def _on_bool(idx: int, _f=field, _c=combo, _card=card) -> None:
                val = _c.itemData(idx)
                filters = dict(getattr(_card, "_dt_filters", {}))
                if val is None:
                    filters.pop(_f, None)
                else:
                    filters[_f] = val
                _card._dt_filters = filters  # type: ignore[attr-defined]
                if getattr(_card, "_dt_remote_service", None):
                    navigate_table_query(_card, page=0, filters=filters)
                elif on_filter_change:
                    _emit_bound_action(
                        _card,
                        on_filter_change,
                        build_datatable_action_payload(_card, page=0, filters=filters),
                    )
                else:
                    all_rows = list(getattr(_card, "_dt_all_rows", getattr(_card, "_dt_rows", [])))
                    reset_table_rows(_card, _apply_filters_local(all_rows, filters))

            combo.currentIndexChanged.connect(_on_bool)

        else:
            widget = QLineEdit()
            widget.setPlaceholderText(f"Filter {col.get('header', field)}…")
            widget.setProperty("ui_role", "datatable_filter_input")
            widget.setFixedHeight(24)

            def _on_text(text: str, _f=field, _card=card) -> None:
                filters = dict(getattr(_card, "_dt_filters", {}))
                if text:
                    filters[_f] = text
                else:
                    filters.pop(_f, None)
                _card._dt_filters = filters  # type: ignore[attr-defined]
                if not on_filter_change:
                    all_rows = list(getattr(_card, "_dt_all_rows", getattr(_card, "_dt_rows", [])))
                    reset_table_rows(_card, _apply_filters_local(all_rows, filters))

            def _on_confirm(_card=card) -> None:
                filters = dict(getattr(_card, "_dt_filters", {}))
                if getattr(_card, "_dt_remote_service", None):
                    navigate_table_query(_card, page=0, filters=filters)
                else:
                    _emit_bound_action(
                        _card,
                        on_filter_change,
                        build_datatable_action_payload(_card, page=0, filters=filters),
                    )

            widget.textChanged.connect(_on_text)
            if on_filter_change:
                widget.returnPressed.connect(_on_confirm)

        c_layout.addWidget(widget)
        if width:
            container.setFixedWidth(int(width))
            layout.addWidget(container)
        else:
            layout.addWidget(container, 1)
        filter_widgets.append((field, widget))

    return bar


# ---------------------------------------------------------------------------
# Table wrapper: custom header + filter row + table (for filter-below-header layout)
# ---------------------------------------------------------------------------

def build_header_bar(
    *,
    model: list[dict[str, Any]],
    action_col: int | None,
    selectable: bool,
    legacy_del_col: int | None,
    remote_action: dict[str, Any] | None = None,
    card: Any = None,
    row_numbers_width: int = 0,
) -> QWidget:
    """Build a QWidget that replicates the table column headers, used when the
    built-in QTableWidget header is hidden to make room for a filter row."""
    bar = QWidget()
    bar.setProperty("ui_role", "datatable_header_bar")
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    if row_numbers_width > 0:
        lbl_rn = QLabel("#")
        lbl_rn.setProperty("ui_role", "datatable_header_label")
        lbl_rn.setContentsMargins(4, 0, 4, 0)
        lbl_rn.setFixedWidth(row_numbers_width)
        layout.addWidget(lbl_rn)

    if action_col is not None:
        spacer = QWidget()
        spacer.setFixedWidth(ACTION_COL_WIDTH)
        layout.addWidget(spacer)

    if selectable:
        spacer = QWidget()
        spacer.setFixedWidth(CHECKBOX_COL_WIDTH)
        layout.addWidget(spacer)

    for col in model:
        width = col.get("width")
        if column_is_remote_sortable(col, remote_action) and card is not None:
            field = str(col.get("field") or "").strip()
            btn = QPushButton(
                header_label_with_sort(
                    col,
                    getattr(card, "_dt_sort", {}),
                    remote_action=remote_action,
                )
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFlat(True)
            btn.setProperty("ui_role", "datatable_header_label")
            btn.setStyleSheet("text-align: left;")

            def _on_sort(_=False, _field=field, _card=card) -> None:
                next_sort = cycle_sort_state(getattr(_card, "_dt_sort", {}), _field)
                _card._dt_sort = next_sort  # type: ignore[attr-defined]
                _card._dt_page = 0  # type: ignore[attr-defined]
                refresh_remote_sort_indicators(_card)
                if getattr(_card, "_dt_remote_service", None):
                    navigate_table_query(_card, page=0, sort=next_sort)
                else:
                    _emit_bound_action(
                        _card,
                        remote_action,
                        build_datatable_action_payload(_card, page=0, sort=next_sort),
                    )

            btn.clicked.connect(_on_sort)
            sort_buttons = getattr(card, "_dt_sort_buttons", {})
            if isinstance(sort_buttons, dict):
                sort_buttons[field] = btn
                card._dt_sort_buttons = sort_buttons  # type: ignore[attr-defined]
            if width:
                btn.setFixedWidth(int(width))
                layout.addWidget(btn)
            else:
                layout.addWidget(btn, 1)
        else:
            lbl = QLabel(str(col.get("header") or col.get("field") or ""))
            lbl.setProperty("ui_role", "datatable_header_label")
            lbl.setContentsMargins(4, 0, 4, 0)
            if width:
                lbl.setFixedWidth(int(width))
                layout.addWidget(lbl)
            else:
                layout.addWidget(lbl, 1)

    if legacy_del_col is not None:
        spacer = QWidget()
        spacer.setFixedWidth(60)
        layout.addWidget(spacer)

    return bar


def wrap_table_with_filters(
    *,
    table: QTableWidget,
    header_bar: QWidget,
    filter_bar: QWidget | None,
) -> QFrame:
    """Return a QFrame containing header_bar / filter_bar / table.
    Hides the table's built-in horizontal header so there is no duplication."""
    table.horizontalHeader().setVisible(False)
    table.setFrameShape(QFrame.Shape.NoFrame)

    wrapper = QFrame()
    wrapper.setProperty("ui_role", "datatable_table_section")
    wrapper.setFrameShape(QFrame.Shape.NoFrame)
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    layout.addWidget(header_bar)
    if filter_bar is not None:
        layout.addWidget(filter_bar)
    layout.addWidget(table)

    return wrapper


# ---------------------------------------------------------------------------
# Selection bar
# ---------------------------------------------------------------------------

def build_selection_bar(
    *,
    selection_actions: list[dict[str, Any]],
    app_instance: Any,
    surface_id: str,
    comp_id: str,
    card: Any,
) -> QWidget:
    icon_default = theme_token("icon.default", app_instance=app_instance)
    bar = QWidget()
    bar.setProperty("ui_role", "datatable_selection_bar")
    bar.setVisible(False)
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(8, 4, 8, 4)
    layout.setSpacing(8)

    count_label = QLabel("0 selected")
    count_label.setProperty("ui_role", "datatable_selection_count")
    layout.addWidget(count_label)
    bar._count_label = count_label  # type: ignore[attr-defined]

    for sa in selection_actions:
        if not _is_visible(sa, app_instance, None):
            continue
        label  = str(sa.get("label") or "")
        action = sa.get("action") or {}
        icon_s = str(sa.get("icon") or "").strip()
        variant = sa.get("variant", "")

        btn = QPushButton(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_s:
            btn.setIcon(get_icon(normalize_icon_name(icon_s), icon_default, 14))
        if variant == "danger":
            btn.setProperty("ui_role", "datatable_sel_btn_danger")
        else:
            btn.setProperty("ui_role", "datatable_sel_btn")

        act_copy = dict(action)

        def _on_click(_=False, _a=act_copy, _card=card) -> None:
            selected_ids  = list(getattr(_card, "_dt_selected_ids", set()))
            all_rows      = list(getattr(_card, "_dt_rows", []))
            selected_rows = [r for r in all_rows if r.get("id") in getattr(_card, "_dt_selected_ids", set())]
            emit_action_spec(
                app_instance,
                _a,
                {"selected_ids": selected_ids, "selected_rows": selected_rows},
                surface_id, comp_id,
            )

        btn.clicked.connect(_on_click)
        layout.addWidget(btn)

    layout.addStretch()
    return bar


def _update_selection_bar(card: Any) -> None:
    bar: QWidget | None = getattr(card, "_dt_selection_bar", None)
    if bar is None:
        return
    selected: set = getattr(card, "_dt_selected_ids", set())
    count = len(selected)
    bar.setVisible(count > 0)
    count_label: QLabel | None = getattr(bar, "_count_label", None)
    if count_label is not None:
        count_label.setText(f"{count} selected")


# ---------------------------------------------------------------------------
# Cell edit handler
# ---------------------------------------------------------------------------

def bind_cell_edit_handler(
    *,
    table: QTableWidget,
    model: list[dict[str, Any]],
    on_cell_edit: dict[str, Any],
    app_instance: Any,
    surface_id: str,
    comp_id: str,
    page: int,
    page_size: int,
    col_offset: int = 0,
    card: Any = None,
) -> None:
    table._old_values = {}  # type: ignore[attr-defined]
    for r in range(table.rowCount()):
        for c_idx, col_def in enumerate(model):
            item = table.item(r, c_idx + col_offset)
            if item:
                if col_def.get("type") == "bool":
                    table._old_values[(r, c_idx)] = item.checkState() == Qt.CheckState.Checked  # type: ignore[attr-defined]
                else:
                    table._old_values[(r, c_idx)] = item.text()  # type: ignore[attr-defined]

    def _on_cell_changed(row: int, col: int) -> None:
        model_col = col - col_offset
        if model_col < 0 or model_col >= len(model):
            return
        col_def = model[model_col]
        if not col_def.get("editable", False):
            return
        item = table.item(row, col)
        if not item:
            return
        if col_def.get("type") == "bool":
            new_val = item.checkState() == Qt.CheckState.Checked
        else:
            new_val = item.text()
        old_val = table._old_values.get((row, model_col))  # type: ignore[attr-defined]
        if new_val == old_val:
            return
        table._old_values[(row, model_col)] = new_val  # type: ignore[attr-defined]
        typed_val = new_val if col_def.get("type") == "bool" else cast_value(new_val, col_def.get("type", "str"))
        if card is not None:
            _update_card_rows(card, row, col_def["field"], typed_val)
        emit_action(
            app_instance,
            on_cell_edit["name"],
            {
                **on_cell_edit.get("context", {}),
                "row_index": row + (page * page_size),
                "field": col_def["field"],
                "old_value": old_val,
                "new_value": typed_val,
                "row_data": get_row_data(table, row, model, col_offset),
                "tableId": comp_id,
            },
            surface_id,
            comp_id,
        )

    table.cellChanged.connect(_on_cell_changed)


# ---------------------------------------------------------------------------
# Pagination bar
# ---------------------------------------------------------------------------

def add_pagination_bar(
    *,
    main_layout: QVBoxLayout,
    page: int,
    page_size: int,
    total_rows: int,
    on_page_change: dict[str, Any] | None,
    app_instance: Any,
    surface_id: str,
    comp_id: str,
    card: Any = None,
) -> None:
    total_pages = max(1, (total_rows + page_size - 1) // page_size)
    bar_widget = QWidget()
    bar_widget.setProperty("ui_role", "datatable_pagination_bar")
    bar_widget.setVisible(total_rows > page_size)
    pag_bar = QHBoxLayout(bar_widget)
    pag_bar.setContentsMargins(0, 4, 0, 0)
    pag_bar.addStretch()

    prev_btn = QPushButton("← Prev")
    prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    prev_btn.setProperty("ui_role", "datatable_pager_btn")
    prev_btn.setEnabled(page > 0)
    if on_page_change:
        def _prev_clicked(_=False, _card=card, _on=on_page_change, _ps=page_size, _sid=surface_id, _cid=comp_id) -> None:
            cur_page = getattr(_card, "_dt_page", 0) if _card is not None else 0
            if _card is not None and getattr(_card, "_dt_remote_service", None):
                navigate_table_query(_card, page=cur_page - 1, page_size=_ps)
            else:
                _emit_bound_action(
                    _card,
                    _on,
                    build_datatable_action_payload(
                        _card,
                        page=cur_page - 1,
                        page_size=_ps,
                    ),
                )
        prev_btn.clicked.connect(_prev_clicked)
    pag_bar.addWidget(prev_btn)

    page_label = QLabel(f"Page {page + 1} of {total_pages}")
    page_label.setProperty("ui_role", "datatable_page_label")
    page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    page_label.setFixedWidth(120)
    pag_bar.addWidget(page_label)

    next_btn = QPushButton("Next →")
    next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    next_btn.setProperty("ui_role", "datatable_pager_btn")
    next_btn.setEnabled(page < total_pages - 1)
    if on_page_change:
        def _next_clicked(_=False, _card=card, _on=on_page_change, _ps=page_size, _sid=surface_id, _cid=comp_id) -> None:
            cur_page = getattr(_card, "_dt_page", 0) if _card is not None else 0
            if _card is not None and getattr(_card, "_dt_remote_service", None):
                navigate_table_query(_card, page=cur_page + 1, page_size=_ps)
            else:
                _emit_bound_action(
                    _card,
                    _on,
                    build_datatable_action_payload(
                        _card,
                        page=cur_page + 1,
                        page_size=_ps,
                    ),
                )
        next_btn.clicked.connect(_next_clicked)
    pag_bar.addWidget(next_btn)

    pag_bar.addStretch()
    main_layout.addWidget(bar_widget)

    if card is not None:
        card._dt_pagination_bar = bar_widget  # type: ignore[attr-defined]
        card._dt_prev_btn   = prev_btn   # type: ignore[attr-defined]
        card._dt_next_btn   = next_btn   # type: ignore[attr-defined]
        card._dt_page_label = page_label  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Store binding
# ---------------------------------------------------------------------------

def normalize_store_key(key: str) -> str:
    if key.startswith("$state."):
        key = key[len("$state."):]
    elif key.startswith("$global."):
        key = key[len("$global."):]
    return key if key.startswith("/") else f"/{key.lstrip('/')}"


class DataTableBinder(QObject):
    def __init__(self, *, card: QFrame, key: str, renderer: Any, store: Any):
        super().__init__(card)
        self.card = card
        self.key = normalize_store_key(key)
        self.renderer = renderer
        self.store = store
        self.store.changed.connect(self._on_state_change)

    def _on_state_change(self, key: str, value: Any) -> None:
        if key == self.key or self.key.startswith(f"{key}/") or key.startswith(f"{self.key}/"):
            new_rows = self.store.get(self.key, None, "auto")
            if isinstance(new_rows, list):
                self.renderer._set_rows(self.card, new_rows)
