from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
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


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _diff_rows(props: Dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for hunk in list(props.get("hunks") or []):
        if not isinstance(hunk, dict):
            continue
        old_start = _to_int(hunk.get("old_start") or hunk.get("oldStart")) or 0
        new_start = _to_int(hunk.get("new_start") or hunk.get("newStart")) or 0
        header = str(hunk.get("header") or f"@@ -{old_start}, +{new_start} @@").strip()
        rows.append({"kind": "hunk", "text": header})

        old_no = old_start
        new_no = new_start
        for line in list(hunk.get("lines") or []):
            if not isinstance(line, dict):
                continue
            line_type = str(line.get("type") or "context").strip().lower()
            text = str(line.get("text") or "")

            explicit_old = _to_int(line.get("old_no") or line.get("oldNo"))
            explicit_new = _to_int(line.get("new_no") or line.get("newNo"))
            if line_type == "remove":
                old_value = explicit_old if explicit_old is not None else old_no
                new_value = explicit_new
                old_no = (old_value or old_no) + 1
            elif line_type == "add":
                old_value = explicit_old
                new_value = explicit_new if explicit_new is not None else new_no
                new_no = (new_value or new_no) + 1
            else:
                old_value = explicit_old if explicit_old is not None else old_no
                new_value = explicit_new if explicit_new is not None else new_no
                old_no = (old_value or old_no) + 1
                new_no = (new_value or new_no) + 1

            rows.append(
                {
                    "kind": "line",
                    "type": line_type,
                    "old": old_value,
                    "new": new_value,
                    "text": text,
                }
            )
    return rows


def _count_delta(rows: list[dict[str, Any]]) -> tuple[int, int]:
    added = sum(1 for row in rows if row.get("kind") == "line" and row.get("type") == "add")
    removed = sum(1 for row in rows if row.get("kind") == "line" and row.get("type") == "remove")
    return added, removed


class CodeDiffRenderer(BaseRenderer):
    component_type = "CodeDiff"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "title": self.PROPERTY,
            "filePath": self.PROPERTY,
            "hunks": self.PROPERTY,
            "oldRevision": self.PROPERTY,
            "newRevision": self.PROPERTY,
            "showLineNumbers": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        del surface_id, app_instance
        root = QFrame()
        root.setObjectName(comp_id)
        root.setProperty("ui_role", "code_diff")
        root.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_label = None
        title_text = str(props.get("title") or "").strip()
        if title_text:
            title_label = QLabel(title_text)
            title_label.setProperty("ui_role", "code_diff_title")
            layout.addWidget(title_label)
        
        header_label = QLabel("")
        header_label.setProperty("ui_role", "code_diff_header")
        layout.addWidget(header_label)

        table = QTableWidget(0, 3)
        table.setObjectName(f"{comp_id}_table")
        table.setProperty("ui_role", "code_diff_table")
        table.setHorizontalHeaderLabels(["old", "new", "text"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.setWordWrap(False)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        layout.addWidget(table)

        # Store references for updates
        root._diff_props = props.copy()
        root._title_label = title_label
        root._header_label = header_label
        root._table = table
        root._comp_id = comp_id

        self._refresh_ui(root)
        return root

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if not hasattr(widget, "_diff_props"):
            super().update_widget_property(widget, prop, value)
            return

        if prop in self.binding_strategies():
            widget._diff_props[prop] = value
            self._refresh_ui(widget)
            return
        
        super().update_widget_property(widget, prop, value)

    def _refresh_ui(self, root: QWidget):
        props = root._diff_props
        title_label = root._title_label
        header_label = root._header_label
        table = root._table

        # Update title if possible
        title_text = str(props.get("title") or "").strip()
        if title_label:
            title_label.setText(title_text)
            title_label.setVisible(bool(title_text))
        elif title_text:
            # If title didn't exist but now does, we'd need to re-render layout,
            # but for now we just skip for simplicity or assume it's pre-created.
            pass

        rows = _diff_rows(props)
        added, removed = _count_delta(rows)
        file_path = str(props.get("filePath") or "edited file").strip()
        old_rev = str(props.get("oldRevision") or "").strip()
        new_rev = str(props.get("newRevision") or "").strip()
        rev_suffix = f"  {old_rev} -> {new_rev}" if old_rev or new_rev else ""
        header_label.setText(f"{file_path}{rev_suffix}    +{added} -{removed}")

        table.setRowCount(len(rows))
        show_line_numbers = bool(props.get("showLineNumbers", True))
        table.setColumnHidden(0, not show_line_numbers)
        table.setColumnHidden(1, not show_line_numbers)

        font = QFont("Monospace")
        font.setStyleHint(QFont.TypeWriter)
        font.setPointSize(10)

        colors = {
            "context": QColor("#0B1220"),
            "add": QColor("#052E16"),
            "remove": QColor("#3F1518"),
            "hunk": QColor("#172554"),
        }

        for index, row in enumerate(rows):
            kind = str(row.get("kind") or "line")
            line_type = str(row.get("type") or "context")
            bg = colors.get("hunk" if kind == "hunk" else line_type, QColor("#0B1220"))

            old_text = ""
            new_text = ""
            prefix = " "
            content = str(row.get("text") or "")

            if kind == "hunk":
                prefix = "@"
            elif line_type == "add":
                new_text = str(row.get("new") or "")
                prefix = "+"
            elif line_type == "remove":
                old_text = str(row.get("old") or "")
                prefix = "-"
            else:
                old_text = str(row.get("old") or "")
                new_text = str(row.get("new") or "")
                prefix = " "

            old_item = QTableWidgetItem(old_text)
            old_item.setFont(font)
            old_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            old_item.setForeground(QColor("#94A3B8"))
            old_item.setBackground(bg)
            table.setItem(index, 0, old_item)

            new_item = QTableWidgetItem(new_text)
            new_item.setFont(font)
            new_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            new_item.setForeground(QColor("#94A3B8"))
            new_item.setBackground(bg)
            table.setItem(index, 1, new_item)

            text_item = QTableWidgetItem(f"{prefix} {content}")
            text_item.setFont(font)
            text_item.setForeground(QColor("#E2E8F0"))
            text_item.setBackground(bg)
            table.setItem(index, 2, text_item)

            if kind == "hunk":
                old_item.setText("")
                new_item.setText("")
                text_item.setForeground(QColor("#BFDBFE"))

            table.setRowHeight(index, 24)
