from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout
from ....animation import fade_in, slide
from ...base import BaseRenderer

class DialogRenderer(BaseRenderer):
    component_type = "Dialog"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children": self.COMPONENT,
            "title": self.PROPERTY,
            "animation": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        title = props.get("title", "Dialog")

        # app_instance is the MainWindow
        # Find existing dialog in the app_instance children
        dialog = app_instance.findChild(QDialog, comp_id)

        if not dialog:
            dialog = QDialog(app_instance)
            dialog.setObjectName(comp_id)
            layout = QVBoxLayout(dialog)
            dialog.setLayout(layout)

            # When the user dismisses via the OS close button (X) or Escape, Qt fires
            # `finished` but no server action is called, leaving _surface_roots["modal"]
            # set. Any subsequent page re-render would then call rerender_mounted_subsurfaces
            # which re-shows the dialog. Clean up here to prevent that.
            def _on_dialog_finished(_result: int, _sid: str = surface_id, _cid: str = comp_id) -> None:
                surface_roots = getattr(app_instance, "_surface_roots", None)
                if isinstance(surface_roots, dict):
                    surface_roots.pop(_sid, None)
                surfaces_map = getattr(app_instance, "surfaces", None)
                if isinstance(surfaces_map, dict):
                    surfaces_map.pop(_sid, None)
                renderer = getattr(app_instance, "renderer", None)
                if renderer is not None:
                    active = getattr(renderer, "active_dialogs", {}).get(_sid, {})
                    active.pop(_cid, None)

            dialog.finished.connect(_on_dialog_finished)

        # Register in active_dialogs for lifecycle management
        if surface_id not in app_instance.renderer.active_dialogs:
            app_instance.renderer.active_dialogs[surface_id] = {}
        app_instance.renderer.active_dialogs[surface_id][comp_id] = dialog

        # Clear existing layout for refresh
        layout = dialog.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                elif item.layout():
                    pass

        dialog.setWindowTitle(title)
        surface = getattr(app_instance, "surfaces", {}).get(surface_id, {})
        options = surface.get("options", {}) if isinstance(surface, dict) else {}
        try:
            width = max(320, int(options.get("width", 500)))
        except Exception:
            width = 500
        dialog.setMinimumWidth(width)
        dialog.setMinimumHeight(400)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        if hasattr(dialog, "setProperty"):
            dialog.setProperty("ui_role", "dialog_shell")

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        if not props.get("animation"):
            end_pos = dialog.pos()
            start_pos = QPoint(end_pos)
            start_pos.setY(end_pos.y() - 28)
            slide(dialog, start=start_pos, end=end_pos, duration=220)
            fade_in(dialog, duration=220, start=0.0, end=1.0)
        return dialog

    def before_children_render(self, widget, props, surface_id, app_instance, comp_id):
        pass

    def after_children_render(self, widget, props, surface_id, app_instance, comp_id):
        pass
