from PySide6.QtWidgets import (
    QWidget,
    QGridLayout,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QPushButton,
    QMenu,
)
from PySide6.QtCore import Qt, QMimeData, QPoint
from PySide6.QtGui import QDrag, QColor, QPalette, QPainter, QAction
from typing import Dict, Any, Optional, cast, List, Tuple
from ...base import BaseRenderer, emit_action
from ..layout.common import apply_children_collection_patch


class SquareGrid(QFrame):
    def __init__(self, cols, rows, parent=None):
        super().__init__(parent)
        self.cols = cols
        self.rows = rows
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(4)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(self.grid_layout)
        self.placeholders: Dict[Tuple[int, int], QWidget] = {}
        self.occupied: List[Tuple[int, int]] = []
    def relayout_widgets(self):
        layout = cast(QGridLayout, self.layout())
        if not layout: return

        self.setUpdatesEnabled(False)
        try:
            occupied = []
            widgets_to_place = []
            for i in reversed(range(layout.count())):
                item = layout.itemAt(i)
                if item and item.widget():
                    child = item.widget()
                    if child and child.property("is_widget"):
                        layout.removeWidget(child)
                        widgets_to_place.append(child)

            remaining_widgets = []
            for child in widgets_to_place:
                pos = child.property("grid_pos")
                if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                    r, c = pos
                    w = child.property("grid_w") or 1
                    h = child.property("grid_h") or 1

                    # Ensure coordinates are within bounds
                    r = max(0, min(int(r), self.rows - 1))
                    c = max(0, min(int(c), self.cols - w))

                    layout.addWidget(child, r, c, h, w)
                    # Mark all cells occupied by this widget
                    for dr in range(h):
                        for dc in range(w):
                            occupied.append((r + dr, c + dc))
                else:
                    remaining_widgets.append(child)

            # Only auto-place widgets that truly have no position
            for child in remaining_widgets:
                w = child.property("grid_w") or 1
                h = child.property("grid_h") or 1

                found = False
                for r in range(self.rows):
                    for c in range(self.cols - w + 1):
                        is_free = True
                        for dr in range(h):
                            for dc in range(w):
                                if (r + dr, c + dc) in occupied:
                                    is_free = False
                                    break
                            if not is_free:
                                break

                        if is_free:
                            # Found a spot
                            layout.addWidget(child, r, c, h, w)
                            for dr in range(h):
                                for dc in range(w):
                                    occupied.append((r + dr, c + dc))
                            found = True
                            break
                    if found:
                        break
                
                if not found:
                    # Last resort: just put it at (0,0) or hide it? 
                    # Let's put it at (0,0) so it's visible at least.
                    layout.addWidget(child, 0, 0, h, w)

            self.occupied = occupied

            edit_mode = self.property("edit_mode")
            for coord, placeholder in self.placeholders.items():
                if coord in occupied:
                    placeholder.setVisible(False)
                else:
                    placeholder.setVisible(True)
                    btn = placeholder.findChild(QPushButton)
                    if btn: btn.setVisible(bool(edit_mode))
                    if not edit_mode:
                        placeholder.setProperty("ui_role", "grid_placeholder_hidden")
                    else:
                        placeholder.setProperty("ui_role", "grid_placeholder_idle")
                    placeholder.style().unpolish(placeholder)
                    placeholder.style().polish(placeholder)

            self.update_square_size()
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_square_size()

    def update_square_size(self):
        # Calculate cell size based on width
        available_w = max(400, self.width() - 20)  # Use min 400 if width not yet ready
        cell_size = (available_w - (self.cols - 1) * 4) // self.cols
        cell_size = max(50, cell_size) # Absolute minimum for visibility

        # Apply to placeholders
        for placeholder in self.placeholders.values():
            placeholder.setFixedSize(cell_size, cell_size)

        # Total height = (cell_size * rows) + (spacing * (rows-1)) + margins
        total_h = (cell_size * self.rows) + ((self.rows - 1) * 4) + 20
        self.setFixedHeight(total_h)

        # Apply to widgets
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if w.property("is_widget"):
                    gw = w.property("grid_w") or 1
                    gh = w.property("grid_h") or 1
                    w.setFixedSize(
                        gw * cell_size + (gw - 1) * 4, gh * cell_size + (gh - 1) * 4
                    )
                    w.setVisible(True) # Ensure it's visible after sizing

class GridDropZoneRenderer(BaseRenderer):
    component_type = "GridDropZone"

    def after_children_render(self, widget, props, surface_id, app_instance):
        if hasattr(widget, "relayout_widgets"):
            widget.relayout_widgets()

    def apply_collection_patch(self, widget, prop, action, value) -> bool:
        if prop != "children":
            return False

        app_instance = getattr(widget, "_app_instance", None)
        comp_id = getattr(widget, "_comp_id", "")
        surface_id = getattr(widget, "_surface_id", "main")
        if not app_instance or not comp_id:
            return False

        from ..layout.common import (
            _find_comp_def,
            _child_ref_id,
            _register_inline_component_tree,
        )
        from ...collection_patch import patch_collection

        comp_def, resolved_surface_id = _find_comp_def(
            app_instance, comp_id, surface_id
        )
        if not isinstance(comp_def, dict):
            return False

        surfaces = getattr(app_instance, "_surfaces", None)
        rerender = getattr(surfaces, "rerender_component", None)
        if callable(rerender):
            rerender(comp_id)
            return True

        if hasattr(widget, "relayout_widgets"):
            widget.relayout_widgets()

        return False

    def add_child_to_widget(self, parent_widget, child_widget):
        layout = parent_widget.layout()
        if layout and isinstance(layout, QGridLayout):
            # Add to (0,0) temporarily; relayout_widgets will reposition it.
            layout.addWidget(child_widget, 0, 0)

    def update_widget_property(self, widget: QWidget, prop: str, value: Any):
        if prop == "edit_mode":
            widget.setProperty("edit_mode", value)
            # Propagate to all child widgets
            if hasattr(widget, "grid_layout"): # Safety check
                for i in range(widget.grid_layout.count()):
                    item = widget.grid_layout.itemAt(i)
                    if item and item.widget():
                        child = item.widget()
                        if child.property("is_widget"): 
                            child.setProperty("edit_mode", value)
                            # Explicitly trigger visual feedback by calling the child's renderer if possible
                            app_instance = child.window()
                            if hasattr(app_instance, "renderer"):
                                child_ren = app_instance.renderer.registry.get("DashboardWidget")
                                if child_ren:
                                    child_ren.update_widget_property(child, "edit_mode", value)
            
            enabled = bool(value)
            widget.setAcceptDrops(enabled)
            occupied = set(getattr(widget, "occupied", []))
            for coord, placeholder in getattr(widget, "placeholders", {}).items():
                if coord in occupied:
                    placeholder.setVisible(False)
                else:
                    placeholder.setVisible(True)
                    self._update_placeholder_style(
                        placeholder,
                        False,
                        edit_mode=enabled,
                    )
            widget.update()
            return
        if prop in {"add_action", "move_action", "session_key"}:
            widget.setProperty(prop, str(value or ""))
            return
        super().update_widget_property(widget, prop, value)

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        cols = props.get("columns", 4)
        rows = props.get("rows", 4)

        widget = SquareGrid(cols, rows)
        widget.setObjectName(comp_id)
        widget.setAcceptDrops(True)
        widget.setProperty("ui_role", "grid_dropzone")

        widget.setMinimumSize(400, 400)

        # Create placeholders
        for r in range(rows):
            for c in range(cols):
                placeholder = QFrame()
                placeholder.setObjectName(f"placeholder_{r}_{c}")
                self._update_placeholder_style(placeholder, False)

                # Add "+" button
                p_layout = QVBoxLayout(placeholder)
                p_layout.setContentsMargins(0, 0, 0, 0)
                p_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                add_btn = QPushButton("+")
                add_btn.setObjectName(f"add_btn_{r}_{c}")
                add_btn.setFixedSize(44, 44)
                add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                add_btn.setProperty("ui_role", "grid_add_btn")
                add_btn.clicked.connect(
                    lambda checked=False, row=r, col=c: self._show_add_menu(
                        widget, row, col, app_instance
                    )
                )
                p_layout.addWidget(add_btn)

                widget.grid_layout.addWidget(placeholder, r, c)
                widget.placeholders[(r, c)] = placeholder

        # Store for internal use
        widget.setProperty("grid_cols", cols)
        widget.setProperty("grid_rows", rows)
        widget.setProperty("last_highlighted", [])

        edit_mode = props.get("edit_mode", False)
        widget.setProperty("edit_mode", edit_mode)
        widget.setAcceptDrops(edit_mode)
        widget.setProperty("add_action", str(props.get("add_action") or "add_widget"))
        widget.setProperty("move_action", str(props.get("move_action") or "move_widget"))
        widget.setProperty("session_key", str(props.get("session_key") or "grid_widgets"))
        widget.setProperty("insertable_items", props.get("insertable_items"))

        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Override drag/drop events
        widget.dragEnterEvent = lambda e: self._dragEnterEvent(widget, e)  # type: ignore
        widget.dragMoveEvent = lambda e: self._dragMoveEvent(widget, e)  # type: ignore
        widget.dragLeaveEvent = lambda e: self._dragLeaveEvent(widget, e)  # type: ignore
        widget.dropEvent = lambda e: self._dropEvent(widget, e, app_instance)  # type: ignore

        widget._surface_id = surface_id  # type: ignore[attr-defined]
        widget._app_instance = app_instance  # type: ignore[attr-defined]
        widget._comp_id = comp_id  # type: ignore[attr-defined]

        return widget

    def _show_add_menu(self, widget, row, col, app_instance):
        # Check if cell is occupied first (safety)
        if hasattr(widget, "occupied") and (row, col) in widget.occupied:
            return

        menu = QMenu(widget)
        menu.setProperty("ui_role", "grid_add_menu")

        insertable_items = widget.property("insertable_items")
        if not insertable_items:
            insertable_items = [
                {"label": "Square", "size": "square"},
                {"label": "Horizontal", "size": "rect_h"},
                {"label": "Vertical", "size": "rect_v"},
            ]

        add_action = str(widget.property("add_action") or "add_widget")
        session_key = str(widget.property("session_key") or "grid_widgets")
        for item in insertable_items:
            label = str(item.get("label", "Item"))
            size = str(item.get("size", "square"))
            
            action = QAction(label, menu)
            action.triggered.connect(
                lambda checked=False, s=size: emit_action(
                    app_instance,
                    add_action,
                    {
                        "size": s,
                        "row": row,
                        "col": col,
                        "grid_id": widget.objectName(),
                        "session_key": session_key,
                    },
                    "main",
                    widget.objectName(),
                )
            )
            menu.addAction(action)

        menu.exec(
            QPushButton.mapToGlobal(
                widget.findChild(QPushButton, f"add_btn_{row}_{col}"), QPoint(0, 0)
            )
        )

    def after_children_render(
        self,
        widget: QWidget,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str,
    ):
        sgrid = cast(SquareGrid, widget)
        sgrid.relayout_widgets()
        # Final cleanup: ensure all widgets are in current_widgets and placed
        sgrid.update_square_size()
        
        # Repaint to ensure immediate visibility
        widget.update()

    def _dragEnterEvent(self, widget, event):
        if event.mimeData().hasFormat("application/x-dashboard-widget"):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.acceptProposedAction()

    def _dragMoveEvent(self, widget, event):
        source = event.source()
        w = source.property("grid_w") or 1
        h = source.property("grid_h") or 1

        # Calculate grid cell from position (adjusting for hotspot)
        hotspot_str = event.mimeData().text()
        offset = QPoint(0, 0)
        if "," in hotspot_str:
            try:
                hx, hy = map(int, hotspot_str.split(","))
                offset = QPoint(hx, hy)
            except: pass
            
        r, c = self._get_grid_pos(widget, event.pos() - offset)

        # Clip base pos so the whole widget stays inside
        cols = widget.property("grid_cols")
        rows = widget.property("grid_rows")
        c = max(0, min(c, cols - w))
        r = max(0, min(r, rows - h))

        # Check for collision in the entire target area
        collision = False
        occupied = getattr(widget, "occupied", [])

        # Exclude source widget's original cells from collision check
        source_cells = []
        source_pos = source.property("grid_pos")
        if source_pos:
            sr, sc = source_pos
            sw = source.property("grid_w") or 1
            sh = source.property("grid_h") or 1
            for s_dr in range(sh):
                for s_dc in range(sw):
                    source_cells.append((sr + s_dr, sc + s_dc))

        target_cells = []
        for dr in range(h):
            for dc in range(w):
                cell = (r + dr, c + dc)
                target_cells.append(cell)
                if cell in occupied and cell not in source_cells:
                    collision = True
                    # Don't break yet, we want to highlight all target cells red

        # Hover feedback
        last_highlighted = widget.property("last_highlighted") or []
        # PySide may convert tuples to lists, convert back for hashing
        last_highlighted = [
            tuple(c) if isinstance(c, list) else c for c in last_highlighted
        ]

        if last_highlighted != target_cells:
            # Reset old highlights
            for prev_cell in last_highlighted:
                if prev_cell in widget.placeholders:
                    self._update_placeholder_style(
                        widget.placeholders[prev_cell], False
                    )

            # Set new highlights
            for cell in target_cells:
                if cell in widget.placeholders:
                    self._update_placeholder_style(
                        widget.placeholders[cell], True, collision=collision
                    )

            widget.setProperty("last_highlighted", target_cells)

        if collision:
            event.ignore()
        else:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.acceptProposedAction()

    def _dragLeaveEvent(self, widget, event):
        last_highlighted = widget.property("last_highlighted") or []
        for cell in last_highlighted:
            c_tuple = tuple(cell) if isinstance(cell, list) else cell
            if c_tuple in widget.placeholders:
                self._update_placeholder_style(widget.placeholders[c_tuple], False)
        widget.setProperty("last_highlighted", [])

    def _dropEvent(self, widget, event, app_instance):
        source = event.source()
        if not source:
            return

        comp_id = source.objectName()
        w = source.property("grid_w") or 1
        h = source.property("grid_h") or 1

        # Calculate grid cell from position (adjusting for hotspot)
        hotspot_str = event.mimeData().text()
        offset = QPoint(0, 0)
        if "," in hotspot_str:
            try:
                hx, hy = map(int, hotspot_str.split(","))
                offset = QPoint(hx, hy)
            except: pass

        r, c = self._get_grid_pos(widget, event.pos() - offset)

        # Proper clipping for multi-cell widgets
        cols = widget.property("grid_cols")
        rows = widget.property("grid_rows")
        c = max(0, min(c, cols - w))
        r = max(0, min(r, rows - h))

        # Collision check again on drop
        occupied = getattr(widget, "occupied", [])

        # Exclude source widget's original cells
        source_cells = []
        source_pos = source.property("grid_pos")
        if source_pos:
            sr, sc = source_pos
            sw = source.property("grid_w") or 1
            sh = source.property("grid_h") or 1
            for s_dr in range(sh):
                for s_dc in range(sw):
                    source_cells.append((sr + s_dr, sc + s_dc))

        for dr in range(h):
            for dc in range(w):
                cell = (r + dr, c + dc)
                if cell in occupied and cell not in source_cells:
                    event.ignore()
                    return

        # Reset hover state
        self._dragLeaveEvent(widget, None)

        # Emit move action to server
        move_action = str(widget.property("move_action") or "move_widget")
        session_key = str(widget.property("session_key") or "grid_widgets")
        emit_action(
            app_instance,
            move_action,
            {
                "id": comp_id,
                "row": r,
                "col": c,
                "grid_id": widget.objectName(),
                "session_key": session_key,
            },
            "main",
            comp_id,
        )

        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def _get_grid_pos(self, widget, local_pos):
        cols = widget.property("grid_cols")
        rows = widget.property("grid_rows")

        # Cell size is now dynamic but square
        available_w = widget.width() - 20
        cell_w = (available_w - (cols - 1) * 4) // cols
        # height is same as width because they are squares
        cell_h = cell_w

        grid_c = int((local_pos.x() - 10) // (cell_w + 4))
        grid_r = int((local_pos.y() - 10) // (cell_h + 4))

        return max(0, min(grid_r, rows - 1)), max(0, min(grid_c, cols - 1))

    def _update_placeholder_style(
        self, placeholder, active, collision=False, edit_mode=True
    ):
        btn = placeholder.findChild(QPushButton)
        if btn:
            btn.setVisible(edit_mode)

        if not edit_mode:
            placeholder.setProperty("ui_role", "grid_placeholder_hidden")
            return

        if active:
            placeholder.setProperty(
                "ui_role", "grid_placeholder_collision" if collision else "grid_placeholder_active"
            )
        else:
            placeholder.setProperty("ui_role", "grid_placeholder_idle")
        placeholder.style().unpolish(placeholder)
        placeholder.style().polish(placeholder)
