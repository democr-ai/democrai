from __future__ import annotations

import json
import re
from typing import Any

import shiboken6
from PySide6.QtCore import QObject, QPoint, Qt, QEvent
from PySide6.QtGui import QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QPlainTextEdit,
    QRubberBand,
    QSplitterHandle,
    QVBoxLayout,
    QWidget,
)


def _is_alive(obj: Any) -> bool:
    try:
        return obj is not None and shiboken6.isValid(obj)
    except Exception:
        return obj is not None


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception as exc:
        return f"<unrepresentable: {type(exc).__name__}: {exc}>"


def _should_skip_dynamic_property(name: str) -> bool:
    # Skip known internal/shiboken properties that can raise converter errors.
    return name.startswith("_PySide") or name.startswith("__qt_")


class DevToolsInspector(QObject):
    """Minimal in-app inspector for QWidget hierarchy and runtime properties."""

    def __init__(self, window: Any):
        super().__init__(window)
        self.window = window
        self._picker_active = False
        self._selected: QWidget | None = None
        self._app = QApplication.instance()
        self._original_styles: dict[int, str] = {}

        self._overlay = QRubberBand(QRubberBand.Shape.Rectangle, window)
        self._overlay.hide()

        self._dock = QDockWidget("Dev Inspector", window)
        self._dock.setObjectName("devtools_inspector")
        self._dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self._dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        panel = QWidget(self._dock)
        root = QVBoxLayout(panel)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        toolbar = QHBoxLayout()
        self._pick_btn = QPushButton("Pick")
        self._pick_btn.setCheckable(True)
        self._pick_btn.toggled.connect(self.set_picker_enabled)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        self._copy_btn = QPushButton("Copy")
        self._copy_btn.clicked.connect(self.copy_dump)
        self._copy_snapshot_btn = QPushButton("Copy Snapshot")
        self._copy_snapshot_btn.clicked.connect(self.copy_snapshot_json)
        toolbar.addWidget(self._pick_btn)
        toolbar.addWidget(self._refresh_btn)
        toolbar.addWidget(self._copy_btn)
        toolbar.addWidget(self._copy_snapshot_btn)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self._selected_label = QLabel("Selected: <none>")
        root.addWidget(self._selected_label)

        self._rules_filter = QLineEdit()
        self._rules_filter.setPlaceholderText(
            "Filter rules (e.g. variant=default shape=round active=true)"
        )
        self._rules_filter.textChanged.connect(self.refresh)
        root.addWidget(self._rules_filter)

        self._rules_list = QListWidget()
        self._rules_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._rules_list.itemSelectionChanged.connect(self._on_rule_selection_changed)
        self._rules_list.setMinimumHeight(140)
        root.addWidget(self._rules_list)

        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        root.addWidget(self._details, 1)

        self._style_label = QLabel("Style Editor (selected widget)")
        root.addWidget(self._style_label)

        self._style_editor = QPlainTextEdit()
        self._style_editor.setPlaceholderText(
            "color: #111;\nbackground: #fff;\nborder: 1px solid #ccc;\n"
        )
        self._style_editor.setMinimumHeight(220)
        root.addWidget(self._style_editor)

        style_actions = QHBoxLayout()
        self._apply_style_btn = QPushButton("Apply")
        self._apply_style_btn.clicked.connect(self.apply_style)
        self._reset_style_btn = QPushButton("Reset")
        self._reset_style_btn.clicked.connect(self.reset_style)
        self._copy_style_btn = QPushButton("Copy CSS")
        self._copy_style_btn.clicked.connect(self.copy_style)
        style_actions.addWidget(self._apply_style_btn)
        style_actions.addWidget(self._reset_style_btn)
        style_actions.addWidget(self._copy_style_btn)
        style_actions.addStretch(1)
        root.addLayout(style_actions)

        self._dock.setWidget(panel)
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock)
        self._dock.hide()
        self._dock.visibilityChanged.connect(self._on_visibility_changed)

        self._toggle_shortcut = QShortcut(QKeySequence("Ctrl+Shift+I"), window)
        self._toggle_shortcut.activated.connect(self.toggle)

    def toggle(self) -> None:
        if self._dock.isVisible():
            self._dock.hide()
            return
        self._dock.show()
        self._dock.raise_()
        # Keep picker off by default so dock resizing works immediately.
        self._pick_btn.setChecked(False)

    def _on_visibility_changed(self, visible: bool) -> None:
        if not visible:
            self._pick_btn.setChecked(False)
            self._overlay.hide()

    def set_picker_enabled(self, enabled: bool) -> None:
        self._picker_active = bool(enabled)
        if self._app is None:
            return
        if self._picker_active:
            self._app.installEventFilter(self)
        else:
            self._app.removeEventFilter(self)
            self._overlay.hide()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        try:
            if not self._picker_active or self._app is None:
                return False
            event_type = event.type()
            if event_type not in {QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress}:
                return False

            widget = self._app.widgetAt(QCursor.pos())
            if not self._inspectable(widget):
                self._overlay.hide()
                return False

            self._highlight(widget)
            if event_type == QEvent.Type.MouseButtonPress:
                self._selected = widget
                self.refresh()
                return True
            return False
        except Exception:
            return False

    def _inspectable(self, widget: Any) -> bool:
        if not _is_alive(widget):
            return False
        if isinstance(widget, QSplitterHandle):
            # Do not intercept resize handles (dock/main splitters).
            return False
        if widget is self._overlay:
            return False
        if self._dock is not None and (widget is self._dock or self._dock.isAncestorOf(widget)):
            return False
        return True

    def _highlight(self, widget: QWidget) -> None:
        if not _is_alive(widget) or not _is_alive(self.window):
            self._overlay.hide()
            return
        top_left_global = widget.mapToGlobal(QPoint(0, 0))
        top_left_local = self.window.mapFromGlobal(top_left_global)
        rect = widget.rect()
        rect.moveTopLeft(top_left_local)
        self._overlay.setGeometry(rect)
        self._overlay.show()

    def refresh(self) -> None:
        widget = self._selected
        if not _is_alive(widget):
            self._selected_label.setText("Selected: <none>")
            if hasattr(self, "_rules_list"):
                self._rules_list.clear()
            self._details.setPlainText("Select a widget with Pick mode to inspect it.")
            self._style_editor.setPlainText("")
            return
        self._selected_label.setText(
            f"Selected: {type(widget).__name__} #{widget.objectName() or '<no-id>'}"
        )
        self._remember_original_style(widget)
        current_style = self._safe_style_sheet(widget)
        if current_style is not None:
            self._style_editor.setPlainText(current_style)
        try:
            self._details.setPlainText(self._widget_dump(widget))
            self._populate_rules_list(widget)
        except Exception as exc:
            self._details.setPlainText(
                "Inspector error while dumping selected widget:\n"
                f"{type(exc).__name__}: {exc}"
            )

    def _safe_style_sheet(self, widget: Any) -> str | None:
        try:
            getter = getattr(widget, "styleSheet", None)
            if callable(getter):
                return str(getter() or "")
        except Exception:
            return None
        return None

    def _safe_app_style_sheet(self) -> str:
        app = self._app
        if app is None:
            return ""
        try:
            return str(app.styleSheet() or "")
        except Exception:
            return ""

    def _filter_query(self) -> str:
        rules_filter = getattr(self, "_rules_filter", None)
        if rules_filter is None:
            return ""
        try:
            return str(rules_filter.text() or "").strip()
        except Exception:
            return ""

    def _widget_class_names(self, widget: Any) -> set[str]:
        names: set[str] = set()
        try:
            meta = widget.metaObject()
            while meta is not None:
                name = str(meta.className() or "").strip()
                if name:
                    names.add(name)
                meta = meta.superClass()
        except Exception:
            pass
        try:
            for cls in type(widget).mro():
                if cls is object:
                    continue
                name = str(getattr(cls, "__name__", "")).strip()
                if name:
                    names.add(name)
        except Exception:
            pass
        return names

    def _safe_widget_property(self, widget: Any, name: str) -> Any:
        try:
            return widget.property(name)
        except Exception:
            return None

    def _selector_matches_widget(self, selector: str, widget: Any) -> bool:
        # Keep only the leaf selector and ignore combinators hierarchy.
        leaf = re.split(r"\s*[>+~\s]\s*", selector.strip())[-1].strip()
        if not leaf:
            return False

        # Ignore pseudo states for structural matching (hover/focus/pressed/etc.).
        leaf = re.sub(r":[a-zA-Z_-][\w-]*", "", leaf)

        id_match = re.search(r"#([A-Za-z_][\w-]*)", leaf)
        if id_match:
            obj_name = ""
            try:
                obj_name = str(widget.objectName() or "")
            except Exception:
                obj_name = ""
            if obj_name != id_match.group(1):
                return False

        class_names = self._widget_class_names(widget)
        type_match = re.match(r"^[A-Za-z_][\w-]*", leaf)
        if type_match:
            type_name = type_match.group(0)
            if type_name != "*" and type_name not in class_names:
                return False

        for attr_name, attr_value in re.findall(r"\[([^\]=]+)=['\"]?([^'\"]+)['\"]?\]", leaf):
            prop = self._safe_widget_property(widget, attr_name.strip())
            if str(prop) != attr_value.strip():
                return False

        for attr_name in re.findall(r"\[([^\]=\s]+)\]", leaf):
            if re.search(rf"\[{re.escape(attr_name)}=", leaf):
                continue
            prop = self._safe_widget_property(widget, attr_name.strip())
            if prop in (None, False, ""):
                return False

        return True

    def _rule_matches_filter(self, rule: str, widget: Any, query: str) -> bool:
        if not query:
            return True
        selector = rule.split("{", 1)[0].strip().lower()
        haystack = rule.lower()
        tokens = [token.strip().lower() for token in query.split() if token.strip()]
        for token in tokens:
            if "=" in token:
                key, value = token.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'\"")
                if not key:
                    continue
                prop = self._safe_widget_property(widget, key)
                if str(prop).strip().lower() != value:
                    return False
                attr_patterns = (
                    f"[{key}={value}]",
                    f"[{key}='{value}']",
                    f'[{key}="{value}"]',
                )
                if not any(pattern in selector for pattern in attr_patterns):
                    return False
                continue
            if token not in haystack:
                return False
        return True

    def _matched_global_rules(self, widget: Any, *, query: str = "") -> list[str]:
        stylesheet = self._safe_app_style_sheet()
        if not stylesheet:
            return []

        ranked: list[tuple[tuple[int, int, int, int], str]] = []
        for selector_block, body in re.findall(r"([^{}]+)\{([^{}]*)\}", stylesheet, flags=re.S):
            selectors = [s.strip() for s in selector_block.split(",") if s.strip()]
            if not selectors:
                continue
            selected = [s for s in selectors if self._selector_matches_widget(s, widget)]
            if not selected:
                continue
            compact_body = " ".join(body.split())
            for order, selector in enumerate(selected):
                ids = len(re.findall(r"#[A-Za-z_][\w-]*", selector))
                attrs = len(re.findall(r"\[[^\]]+\]", selector))
                pseudos = len(re.findall(r":[a-zA-Z_-][\w-]*", selector))
                type_match = re.match(r"^[A-Za-z_][\w-]*", selector.strip())
                types = 1 if type_match else 0
                specificity = (ids, attrs + pseudos, types, -order)
                rule = f"{selector} {{ {compact_body} }}"
                if not self._rule_matches_filter(rule, widget, query):
                    continue
                ranked.append((specificity, rule))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in ranked]

    def _selected_rule_text(self) -> str:
        rules_list = getattr(self, "_rules_list", None)
        if rules_list is None:
            return ""
        try:
            current_item = rules_list.currentItem()
            if current_item is None:
                return ""
            return str(current_item.text() or "")
        except Exception:
            return ""

    def _populate_rules_list(self, widget: Any) -> None:
        rules_list = getattr(self, "_rules_list", None)
        if rules_list is None:
            return
        query = self._filter_query()
        rules = self._matched_global_rules(widget, query=query)
        rules_list.clear()
        for rule in rules:
            item = QListWidgetItem(rule)
            item.setToolTip(rule)
            rules_list.addItem(item)

    def _on_rule_selection_changed(self) -> None:
        widget = self._selected
        if not _is_alive(widget):
            return
        try:
            self._details.setPlainText(self._widget_dump(widget))
        except Exception:
            return

    def _remember_original_style(self, widget: Any) -> None:
        if not _is_alive(widget):
            return
        key = id(widget)
        if key in self._original_styles:
            return
        current_style = self._safe_style_sheet(widget)
        if current_style is not None:
            self._original_styles[key] = current_style

    def apply_style(self) -> None:
        widget = self._selected
        if not _is_alive(widget):
            return
        self._remember_original_style(widget)
        css = self._style_editor.toPlainText()
        try:
            widget.setStyleSheet(css)
        except Exception as exc:
            self._details.setPlainText(f"Style apply error:\n{type(exc).__name__}: {exc}")

    def reset_style(self) -> None:
        widget = self._selected
        if not _is_alive(widget):
            return
        original = self._original_styles.get(id(widget), "")
        try:
            widget.setStyleSheet(original)
            self._style_editor.setPlainText(original)
        except Exception as exc:
            self._details.setPlainText(f"Style reset error:\n{type(exc).__name__}: {exc}")

    def copy_style(self) -> None:
        if self._app is None:
            return
        clipboard = self._app.clipboard()
        if clipboard is not None:
            clipboard.setText(self._style_editor.toPlainText())

    def copy_dump(self) -> None:
        if self._app is None:
            return
        clipboard = self._app.clipboard()
        if clipboard is not None:
            clipboard.setText(self._details.toPlainText())

    def _collect_widget_snapshot(self, widget: QWidget) -> dict[str, Any]:
        geom = widget.geometry()
        dynamic_props: dict[str, Any] = {}
        try:
            prop_names = [
                bytes(name).decode("utf-8", "replace")
                for name in widget.dynamicPropertyNames()
            ]
        except Exception:
            prop_names = []
        for name in sorted(prop_names):
            if _should_skip_dynamic_property(name):
                continue
            dynamic_props[name] = _safe_repr(self._safe_widget_property(widget, name))

        query = self._filter_query()
        return {
            "class": type(widget).__name__,
            "object_name": widget.objectName() or "",
            "geometry": {
                "x": geom.x(),
                "y": geom.y(),
                "w": geom.width(),
                "h": geom.height(),
            },
            "visible": bool(widget.isVisible()),
            "enabled": bool(widget.isEnabled()),
            "style_source": (
                "widget_override + app_global"
                if bool(self._safe_style_sheet(widget))
                else ("app_global_only" if self._matched_global_rules(widget) else "none")
            ),
            "widget_stylesheet": self._safe_style_sheet(widget) or "",
            "filter_query": query,
            "matched_global_rules": self._matched_global_rules(widget, query=query),
            "selected_rule": self._selected_rule_text(),
            "dynamic_properties": dynamic_props,
        }

    def copy_snapshot_json(self) -> None:
        widget = self._selected
        if not _is_alive(widget) or self._app is None:
            return
        snapshot = self._collect_widget_snapshot(widget)
        payload = json.dumps(snapshot, ensure_ascii=True, indent=2, sort_keys=True)
        clipboard = self._app.clipboard()
        if clipboard is not None:
            clipboard.setText(payload)

    def _widget_dump(self, widget: QWidget) -> str:
        lines: list[str] = []
        lines.append(f"class: {type(widget).__name__}")
        lines.append(f"objectName: {widget.objectName()!r}")
        geom = widget.geometry()
        lines.append(f"geometry: x={geom.x()} y={geom.y()} w={geom.width()} h={geom.height()}")
        lines.append(f"visible: {widget.isVisible()} enabled: {widget.isEnabled()}")

        parent = widget.parentWidget()
        if parent is not None:
            lines.append(
                f"parent: {type(parent).__name__} #{parent.objectName() or '<no-id>'}"
            )
        else:
            lines.append("parent: <none>")

        lines.append("dynamic_properties:")
        names = []
        try:
            names = [
                bytes(name).decode("utf-8", "replace")
                for name in widget.dynamicPropertyNames()
            ]
        except Exception:
            names = []
        if not names:
            lines.append("  (none)")
        else:
            for name in sorted(names):
                if _should_skip_dynamic_property(name):
                    lines.append("  " + name + ": " + "<internal: skipped>")
                    continue
                try:
                    value = widget.property(name)
                except Exception as exc:
                    value = f"<unavailable: {type(exc).__name__}: {exc}>"
                lines.append(f"  {name}: {_safe_repr(value)}")

        style = widget.styleSheet() if hasattr(widget, "styleSheet") else ""
        query = self._filter_query()
        matched_rules = self._matched_global_rules(widget, query=query)
        if style:
            source = "widget_override + app_global"
        elif matched_rules:
            source = "app_global_only"
        else:
            source = "none"
        lines.append(f"style_source: {source}")
        if query:
            lines.append(f"rules_filter: {query}")
        selected_rule = self._selected_rule_text()
        if selected_rule:
            lines.append(f"selected_rule: {selected_rule}")
        lines.append("widget_stylesheet:")
        lines.append(style if style else "  (empty)")
        lines.append("matched_global_rules:")
        if not matched_rules:
            lines.append("  (none)")
        else:
            limit = 80
            for row in matched_rules[:limit]:
                lines.append(f"  {row}")
            if len(matched_rules) > limit:
                lines.append(f"  ... ({len(matched_rules) - limit} more)")
        return "\n".join(lines)


def setup_devtools(window: Any, *, enabled: bool) -> Any | None:
    if not enabled:
        return None
    try:
        return DevToolsInspector(window)
    except Exception:
        return None
