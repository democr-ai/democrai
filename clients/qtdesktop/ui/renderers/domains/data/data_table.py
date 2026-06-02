from __future__ import annotations
from typing import Any
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
from ...base import BaseRenderer, emit_action, emit_action_spec
from ...collection_patch import patch_collection
from .datatable_support import (
    DataTableBinder,
    add_pagination_bar,
    bind_cell_edit_handler,
    build_datatable_action_payload,
    build_filter_bar,
    build_header_bar,
    build_selection_bar,
    cycle_sort_state,
    compute_layout,
    configure_table,
    normalize_action_spec,
    normalize_sort_state,
    parse_table_query_state,
    populate_row,
    query_state_key,
    qt_object_alive,
    refresh_remote_sort_indicators,
    reset_table_rows,
    wrap_table_with_filters,
    get_current_path,
    navigate_table_query,
)


class DataTableRenderer(BaseRenderer):
    component_type = "DataTable"

    def binding_strategies(self) -> dict[str, str]:
        return {
            **super().binding_strategies(),
            "rows": self.PROPERTY,
            "model": self.COMPONENT,
            "page": self.PROPERTY,
            "page_size": self.PROPERTY,
            "total_rows": self.PROPERTY,
            "sort": self.PROPERTY,
        }

    def render(
        self,
        props: dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ) -> QWidget:
        model: list[dict[str, Any]] = props.get("model", [])
        rows: list[dict[str, Any]] = props.get("rows", [])
        page: int = props.get("page", 0)
        page_size: int = props.get("page_size", 25)
        total_rows: int = props.get("total_rows", len(rows))
        show_row_numbers: bool = props.get("show_row_numbers", False)
        selectable: bool = bool(props.get("selectable", False))
        paginated: bool = bool(props.get("paginated", props.get("pagination", True)))
        row_actions: list | None = props.get("row_actions") or None
        selection_actions: list = props.get("selection_actions") or []

        remote_service = normalize_action_spec(props.get("remote_service"))
        on_page_change = normalize_action_spec(props.get("on_page_change")) or remote_service
        on_cell_edit = props.get("on_cell_edit")
        on_row_add = props.get("on_row_add")
        on_row_delete = props.get("on_row_delete")
        on_filter_change = normalize_action_spec(props.get("on_filter_change")) or remote_service
        auto_refresh = props.get("auto_refresh")
        sort_state = normalize_sort_state(props.get("sort") or {})
        filters_state = dict(props.get("filters") or {})

        if remote_service is not None:
            query_state = parse_table_query_state(
                get_current_path(app_instance),
                comp_id,
                default_page=page,
                default_page_size=page_size,
                default_filters=filters_state,
                default_sort=sort_state,
            )
            page = int(query_state.get("page", page) or page)
            page_size = int(query_state.get("page_size", page_size) or page_size)
            filters_state = dict(query_state.get("filters") or filters_state)
            sort_state = normalize_sort_state(query_state.get("sort") or sort_state)

        card = QFrame()
        card.setObjectName(comp_id)
        card.setAutoFillBackground(True)
        card.setProperty("ui_role", "datatable_card")

        main_layout = QVBoxLayout(card)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(8)

        # ---- Selection bar (hidden until rows are selected) ----
        if selectable and selection_actions:
            sel_bar = build_selection_bar(
                selection_actions=selection_actions,
                app_instance=app_instance,
                surface_id=surface_id,
                comp_id=comp_id,
                card=card,
            )
            card._dt_selection_bar = sel_bar  # type: ignore[attr-defined]
            card._dt_selected_ids = set()  # type: ignore[attr-defined]
            main_layout.addWidget(sel_bar)

        # ---- Toolbar: row count + Add button ----
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        if total_rows > 0:
            info_label = QLabel(f"{total_rows} rows")
            info_label.setProperty("ui_role", "datatable_info_label")
            toolbar.addWidget(info_label)
            card._dt_info_label = info_label  # type: ignore[attr-defined]
        toolbar.addStretch()
        if model:
            columns_btn = QPushButton("Columns")
            columns_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            columns_btn.setProperty("ui_role", "datatable_columns_btn")
            columns_btn.clicked.connect(lambda _=False, c=card, b=columns_btn: self._show_columns_menu(c, b))
            toolbar.addWidget(columns_btn)
        if on_row_add:
            add_btn = QPushButton("+ Add row")
            add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            add_btn.setProperty("ui_role", "datatable_add_btn")
            add_btn.clicked.connect(
                lambda: emit_action_spec(
                    app_instance,
                    on_row_add,
                    {},
                    surface_id,
                    comp_id,
                )
            )
            toolbar.addWidget(add_btn)
        main_layout.addLayout(toolbar)

        # ---- Compute layout once for filter bar and table ----
        col_offset, action_col, legacy_del_col, _ = compute_layout(
            selectable=selectable,
            model=model,
            row_actions=row_actions,
            on_row_delete=on_row_delete,
        )

        # ---- Table (created first so configure_table runs before filter bar) ----
        table = QTableWidget(len(rows), 0)
        table.setObjectName(f"{comp_id}_table")
        configure_table(
            table=table,
            model=model,
            on_row_delete=on_row_delete,
            show_row_numbers=show_row_numbers,
            selectable=selectable,
            row_actions=row_actions,
            remote_action=remote_service,
            sort_state=sort_state,
        )

        # ---- Filter bar ----
        row_numbers_width = 36 if show_row_numbers else 0
        card._dt_filters = {}  # type: ignore[attr-defined]
        filter_bar = build_filter_bar(
            model=model,
            action_col=action_col,
            selectable=selectable,
            on_filter_change=on_filter_change,
            app_instance=app_instance,
            surface_id=surface_id,
            comp_id=comp_id,
            card=card,
            row_numbers_width=row_numbers_width,
        )

        table.blockSignals(True)
        for row_idx, row_data in enumerate(rows):
            populate_row(
                table=table,
                row_idx=row_idx,
                row_data=row_data,
                model=model,
                on_row_delete=on_row_delete,
                surface_id=surface_id,
                comp_id=comp_id,
                app_instance=app_instance,
                selectable=selectable,
                row_actions=row_actions,
                col_offset=col_offset,
                action_col=action_col,
                legacy_del_col=legacy_del_col,
                card=card,
            )
        table.blockSignals(False)

        if on_cell_edit:
            bind_cell_edit_handler(
                table=table,
                model=model,
                on_cell_edit=on_cell_edit,
                app_instance=app_instance,
                surface_id=surface_id,
                comp_id=comp_id,
                page=page,
                page_size=page_size,
                col_offset=col_offset,
                card=card,
            )

        card._dt_table = table  # type: ignore[attr-defined]
        card._dt_model = model  # type: ignore[attr-defined]
        card._dt_props = props  # type: ignore[attr-defined]
        card._dt_app = app_instance  # type: ignore[attr-defined]
        card._dt_surface_id = surface_id  # type: ignore[attr-defined]
        card._dt_comp_id = comp_id  # type: ignore[attr-defined]
        card._dt_remote_service = remote_service  # type: ignore[attr-defined]
        card._dt_rows = list(rows)  # type: ignore[attr-defined]
        card._dt_all_rows = list(rows)  # type: ignore[attr-defined]  — unfiltered snapshot for client-side filter
        card._dt_filters = dict(filters_state)  # type: ignore[attr-defined]
        card._dt_sort = dict(sort_state)  # type: ignore[attr-defined]
        card._dt_sort_buttons = {}  # type: ignore[attr-defined]
        card._dt_col_offset = col_offset  # type: ignore[attr-defined]
        card._dt_action_col = action_col  # type: ignore[attr-defined]
        card._dt_legacy_del_col = legacy_del_col  # type: ignore[attr-defined]
        card._dt_page = page  # type: ignore[attr-defined]
        card._dt_page_size = page_size  # type: ignore[attr-defined]
        card._dt_total_rows = total_rows  # type: ignore[attr-defined]

        if remote_service is not None:
            header = table.horizontalHeader()

            def _on_header_clicked(section: int, _card=card, _header=header) -> None:
                model_index = section - getattr(_card, "_dt_col_offset", 0)
                if model_index < 0 or model_index >= len(getattr(_card, "_dt_model", [])):
                    return
                column = getattr(_card, "_dt_model", [])[model_index]
                field = str(column.get("field") or "").strip()
                if not field or column.get("sortable") is False:
                    return
                next_sort = cycle_sort_state(getattr(_card, "_dt_sort", {}), field)
                _card._dt_sort = next_sort  # type: ignore[attr-defined]
                _card._dt_page = 0  # type: ignore[attr-defined]
                refresh_remote_sort_indicators(_card)
                navigate_table_query(_card, page=0, sort=next_sort)

            header.sectionClicked.connect(_on_header_clicked)

        # ---- Add table section: wrap with custom header + filter if filterable ----
        if filter_bar is not None:
            header_bar = build_header_bar(
                model=model,
                action_col=action_col,
                selectable=selectable,
                legacy_del_col=legacy_del_col,
                remote_action=remote_service,
                card=card,
                row_numbers_width=row_numbers_width,
            )
            self._register_column_widgets(card, header_bar, filter_bar)
            main_layout.addWidget(
                wrap_table_with_filters(
                    table=table, header_bar=header_bar, filter_bar=filter_bar
                )
            )
        else:
            main_layout.addWidget(table)

        if props.get("auto-height", False):
            self._schedule_fit_table_height(table)

        # ---- Pagination bar ----
        if paginated:
            add_pagination_bar(
                main_layout=main_layout,
                page=page,
                page_size=page_size,
                total_rows=total_rows,
                on_page_change=on_page_change,
                app_instance=app_instance,
                surface_id=surface_id,
                comp_id=comp_id,
                card=card,
            )

        refresh_remote_sort_indicators(card)

        rows_prop = props.get("rows")
        if isinstance(rows_prop, str) and (
            rows_prop.startswith("$state.") or rows_prop.startswith("$global.")
        ):
            DataTableBinder(
                card=card, key=rows_prop, renderer=self, store=app_instance.store
            )

        if remote_service is not None:
            QTimer.singleShot(0, lambda c=card, action=remote_service: self._load_remote_rows(c, action))
            self._bind_query_watch(card, remote_service)

        if auto_refresh and (remote_service is not None or on_page_change is not None):
            self._setup_auto_refresh(
                card=card,
                seconds=int(auto_refresh),
                action=remote_service or on_page_change,
            )

        return card

    def _register_column_widgets(
        self,
        card: QWidget,
        header_bar: QWidget | None,
        filter_bar: QWidget | None,
    ) -> None:
        model = getattr(card, "_dt_model", []) or []
        col_offset = getattr(card, "_dt_col_offset", 0)
        action_col = getattr(card, "_dt_action_col", None)
        props = getattr(card, "_dt_props", {})
        row_numbers_width = 36 if props.get("show_row_numbers") else 0
        base_index = 0
        if row_numbers_width > 0:
            base_index += 1
        if action_col is not None:
            base_index += 1
        if props.get("selectable"):
            base_index += 1

        controls: list[dict[str, Any]] = []
        header_layout = header_bar.layout() if header_bar is not None else None
        filter_layout = filter_bar.layout() if filter_bar is not None else None
        for index, column in enumerate(model):
            controls.append(
                {
                    "field": str(column.get("field") or index),
                    "label": str(column.get("header") or column.get("field") or index),
                    "table_column": index + col_offset,
                    "header_widget": (
                        header_layout.itemAt(base_index + index).widget()
                        if header_layout is not None and header_layout.itemAt(base_index + index) is not None
                        else None
                    ),
                    "filter_widget": (
                        filter_layout.itemAt(base_index + index).widget()
                        if filter_layout is not None and filter_layout.itemAt(base_index + index) is not None
                        else None
                    ),
                }
            )
        card._dt_column_controls = controls  # type: ignore[attr-defined]

    def _show_columns_menu(self, card: QWidget, button: QPushButton) -> None:
        controls = getattr(card, "_dt_column_controls", None)
        if not isinstance(controls, list) or not controls:
            model = getattr(card, "_dt_model", []) or []
            col_offset = getattr(card, "_dt_col_offset", 0)
            controls = [
                {
                    "field": str(column.get("field") or index),
                    "label": str(column.get("header") or column.get("field") or index),
                    "table_column": index + col_offset,
                    "header_widget": None,
                    "filter_widget": None,
                }
                for index, column in enumerate(model)
                if isinstance(column, dict)
            ]
            card._dt_column_controls = controls  # type: ignore[attr-defined]

        table = getattr(card, "_dt_table", None)
        if table is None:
            return

        menu = QMenu(button)
        for control in controls:
            table_column = int(control["table_column"])
            action = menu.addAction(str(control["label"]))
            action.setCheckable(True)
            action.setChecked(not table.isColumnHidden(table_column))

            def _toggle(checked: bool, _control=control, _action=action) -> None:
                visible_count = sum(
                    1
                    for item in controls
                    if not table.isColumnHidden(int(item["table_column"]))
                )
                target_col = int(_control["table_column"])
                if not checked and visible_count <= 1:
                    _action.setChecked(True)
                    return
                table.setColumnHidden(target_col, not checked)
                header_widget = _control.get("header_widget")
                if header_widget is not None:
                    header_widget.setVisible(checked)
                filter_widget = _control.get("filter_widget")
                if filter_widget is not None:
                    filter_widget.setVisible(checked)

            action.toggled.connect(_toggle)

        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _bind_query_watch(self, card: QWidget, action: dict[str, Any] | None) -> None:
        if action is None:
            return
        app = getattr(card, "_dt_app", None)
        store = getattr(app, "store", None)
        if store is None or not hasattr(store, "changed"):
            return
        table_id = str(getattr(card, "_dt_comp_id", "") or "")
        if not table_id:
            return
        card._dt_query_key = query_state_key(get_current_path(app), table_id)  # type: ignore[attr-defined]

        def _on_store_change(key: str, value: Any, _card=card, _action=action, _table_id=table_id) -> None:
            if not qt_object_alive(_card):
                return
            if key != "/current_path":
                return
            path = str(value or "/")
            next_key = query_state_key(path, _table_id)
            if next_key == getattr(_card, "_dt_query_key", ""):
                return
            _card._dt_query_key = next_key  # type: ignore[attr-defined]
            query_state = parse_table_query_state(
                path,
                _table_id,
                default_page=int(getattr(_card, "_dt_page", 0) or 0),
                default_page_size=int(getattr(_card, "_dt_page_size", 25) or 25),
                default_filters=dict(getattr(_card, "_dt_filters", {}) or {}),
                default_sort=dict(getattr(_card, "_dt_sort", {}) or {}),
            )
            _card._dt_page = int(query_state.get("page", 0) or 0)  # type: ignore[attr-defined]
            _card._dt_page_size = int(query_state.get("page_size", 25) or 25)  # type: ignore[attr-defined]
            _card._dt_filters = dict(query_state.get("filters") or {})  # type: ignore[attr-defined]
            _card._dt_sort = dict(query_state.get("sort") or {})  # type: ignore[attr-defined]
            refresh_remote_sort_indicators(_card)
            self._refresh_pagination_controls(_card)
            self._load_remote_rows(_card, _action)

        store.changed.connect(_on_store_change)
        card._dt_query_watch = _on_store_change  # type: ignore[attr-defined]

        def _disconnect_query_watch() -> None:
            try:
                store.changed.disconnect(_on_store_change)
            except (RuntimeError, TypeError):
                pass

        card.destroyed.connect(_disconnect_query_watch)

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "rows":
            rows = list(value) if isinstance(value, list) else []
            widget._dt_all_rows = list(rows)  # type: ignore[attr-defined]
            reset_table_rows(widget, rows)
            if not rows and getattr(widget, "_dt_total_rows", None) not in {0, None}:
                widget._dt_total_rows = 0  # type: ignore[attr-defined]
                self._refresh_pagination_controls(widget)
            table = getattr(widget, "_dt_table", None)
            if table is not None and getattr(widget, "_dt_props", {}).get("auto-height", False):
                self._schedule_fit_table_height(table)
            return
        if prop == "page":
            new_page = int(value) if value is not None else 0
            widget._dt_page = new_page  # type: ignore[attr-defined]
            self._refresh_pagination_controls(widget)
            return
        if prop == "page_size":
            widget._dt_page_size = int(value) if value is not None else 25  # type: ignore[attr-defined]
            self._refresh_pagination_controls(widget)
            return
        if prop == "total_rows":
            widget._dt_total_rows = int(value) if value is not None else 0  # type: ignore[attr-defined]
            info_label = getattr(widget, "_dt_info_label", None)
            if info_label is not None:
                info_label.setText(f"{widget._dt_total_rows} rows")
            self._refresh_pagination_controls(widget)
            return
        if prop == "sort":
            widget._dt_sort = normalize_sort_state(value)  # type: ignore[attr-defined]
            refresh_remote_sort_indicators(widget)
            return
        super().update_widget_property(widget, prop, value)

    def _schedule_fit_table_height(self, table: QTableWidget | None) -> None:
        if table is None:
            return
        QTimer.singleShot(0, lambda t=table: self._fit_table_height(t))

    def _fit_table_height(self, table: QTableWidget) -> None:
        if table is None:
            return
        table.resizeRowsToContents()
        header = table.horizontalHeader()
        header_h = header.height() if header is not None and header.isVisible() else 0
        rows_h = sum(table.rowHeight(i) for i in range(table.rowCount()))
        frame_h = table.frameWidth() * 2
        extra = 2
        total_h = max(40, header_h + rows_h + frame_h + extra)
        table.setMinimumHeight(total_h)
        table.setMaximumHeight(total_h)

    def _refresh_pagination_controls(self, widget: QWidget) -> None:
        page = getattr(widget, "_dt_page", 0)
        page_size = getattr(widget, "_dt_page_size", 25)
        total_rows = getattr(widget, "_dt_total_rows", 0)
        pagination_bar = getattr(widget, "_dt_pagination_bar", None)
        prev_btn = getattr(widget, "_dt_prev_btn", None)
        next_btn = getattr(widget, "_dt_next_btn", None)
        page_label = getattr(widget, "_dt_page_label", None)
        if pagination_bar is not None:
            pagination_bar.setVisible(total_rows > page_size)
        if prev_btn is None and next_btn is None:
            return
        total_pages = max(1, (total_rows + page_size - 1) // page_size)
        if prev_btn is not None:
            prev_btn.setEnabled(page > 0)
        if next_btn is not None:
            next_btn.setEnabled(page < total_pages - 1)
        if page_label is not None:
            page_label.setText(f"Page {page + 1} of {total_pages}")

    def _load_remote_rows(self, card: QWidget, action: dict[str, Any] | None) -> None:
        if action is None:
            return
        app = getattr(card, "_dt_app", None)
        if app is None:
            return
        emit_action(
            app,
            action["name"],
            {**action.get("context", {}), **build_datatable_action_payload(card)},
            getattr(card, "_dt_surface_id", "main"),
            getattr(card, "_dt_comp_id", ""),
        )

    def _setup_auto_refresh(
        self,
        *,
        card: QWidget,
        seconds: int,
        action: dict[str, Any] | None,
    ) -> None:
        if action is None or seconds <= 0:
            return
        timer = QTimer(card)
        timer.setInterval(max(1, seconds) * 1000)
        timer.timeout.connect(
            lambda c=card, a=action: self._load_remote_rows_for_refresh(c, a)
        )
        timer.start()
        card._dt_auto_refresh_timer = timer  # type: ignore[attr-defined]

    def _load_remote_rows_for_refresh(
        self,
        card: QWidget,
        action: dict[str, Any] | None,
    ) -> None:
        if action is None:
            return
        app = getattr(card, "_dt_app", None)
        if app is None:
            return
        emit_action(
            app,
            action["name"],
            {
                **action.get("context", {}),
                **build_datatable_action_payload(card, auto_refresh=True),
            },
            getattr(card, "_dt_surface_id", "main"),
            getattr(card, "_dt_comp_id", ""),
        )

    def apply_collection_patch(
        self, widget: QWidget, prop: str, action: str, value: Any
    ) -> bool:
        if prop != "rows":
            return False

        rows = list(getattr(widget, "_dt_rows", []))
        table = getattr(widget, "_dt_table", None)
        model = getattr(widget, "_dt_model", None)
        props = getattr(widget, "_dt_props", {})
        col_offset = getattr(widget, "_dt_col_offset", 0)
        action_col = getattr(widget, "_dt_action_col", None)
        legacy_del_col = getattr(widget, "_dt_legacy_del_col", None)
        on_row_delete = props.get("on_row_delete")
        row_actions = props.get("row_actions") or None
        selectable = bool(props.get("selectable", False))
        surface_id = getattr(widget, "_dt_surface_id", "main")
        comp_id = getattr(widget, "_dt_comp_id", widget.objectName())
        app_instance = getattr(widget, "_dt_app", None)
        if table is None or model is None or app_instance is None:
            return False

        patch = patch_collection(rows, action, value)
        if not patch.handled:
            return False

        if action == "append":
            table.blockSignals(True)
            for row_data in patch.appended or []:
                row_idx = table.rowCount()
                table.insertRow(row_idx)
                populate_row(
                    table=table,
                    row_idx=row_idx,
                    row_data=row_data,
                    model=model,
                    on_row_delete=on_row_delete,
                    surface_id=surface_id,
                    comp_id=comp_id,
                    app_instance=app_instance,
                    selectable=selectable,
                    row_actions=row_actions,
                    col_offset=col_offset,
                    action_col=action_col,
                    legacy_del_col=legacy_del_col,
                    card=widget,
                )
                rows.append(row_data)
            table.blockSignals(False)
            widget._dt_rows = rows  # type: ignore[attr-defined]
            if props.get("auto-height", False):
                self._schedule_fit_table_height(table)
            return True

        if action == "remove":
            index = patch.index
            if index is None:
                return True
            table.blockSignals(True)
            table.removeRow(index)
            table.blockSignals(False)
            rows.pop(index)
            widget._dt_rows = rows  # type: ignore[attr-defined]
            if props.get("auto-height", False):
                self._schedule_fit_table_height(table)
            return True

        if action == "replace":
            index = patch.index
            replacement = patch.replacement
            if index is None or replacement is None:
                return True
            table.blockSignals(True)
            populate_row(
                table=table,
                row_idx=index,
                row_data=replacement,
                model=model,
                on_row_delete=on_row_delete,
                surface_id=surface_id,
                comp_id=comp_id,
                app_instance=app_instance,
                selectable=selectable,
                row_actions=row_actions,
                col_offset=col_offset,
                action_col=action_col,
                legacy_del_col=legacy_del_col,
                card=widget,
            )
            table.blockSignals(False)
            rows[index] = replacement
            widget._dt_rows = rows  # type: ignore[attr-defined]
            if props.get("auto-height", False):
                self._schedule_fit_table_height(table)
            return True

        if action == "set":
            self._set_rows(widget, list(patch.items))
            return True

        return True

    def _set_rows(self, widget: QWidget, rows: list[dict[str, Any]]) -> None:
        table = getattr(widget, "_dt_table", None)
        model = getattr(widget, "_dt_model", None)
        props = getattr(widget, "_dt_props", {})
        col_offset = getattr(widget, "_dt_col_offset", 0)
        action_col = getattr(widget, "_dt_action_col", None)
        legacy_del_col = getattr(widget, "_dt_legacy_del_col", None)
        on_row_delete = props.get("on_row_delete")
        row_actions = props.get("row_actions") or None
        selectable = bool(props.get("selectable", False))
        surface_id = getattr(widget, "_dt_surface_id", "main")
        comp_id = getattr(widget, "_dt_comp_id", widget.objectName())
        app_instance = getattr(widget, "_dt_app", None)
        if table is None or model is None or app_instance is None:
            return

        table.blockSignals(True)
        table.setRowCount(0)
        table.setRowCount(len(rows))
        for row_idx, row_data in enumerate(rows):
            populate_row(
                table=table,
                row_idx=row_idx,
                row_data=row_data,
                model=model,
                on_row_delete=on_row_delete,
                surface_id=surface_id,
                comp_id=comp_id,
                app_instance=app_instance,
                selectable=selectable,
                row_actions=row_actions,
                col_offset=col_offset,
                action_col=action_col,
                legacy_del_col=legacy_del_col,
                card=widget,
            )
        table.blockSignals(False)
        widget._dt_rows = rows  # type: ignore[attr-defined]
        if props.get("auto-height", False):
            self._schedule_fit_table_height(table)
