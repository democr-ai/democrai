from __future__ import annotations

import os
from typing import Any, cast

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget
from ...state_store import _deep_merge

from ..animation import fade_in, fade_out, slide, stop_animations
from .surface_render_ops import (
    animate_drawer_exit,
    render_tree,
    rerender_component,
    rerender_mounted_subsurfaces,
)
from .log_safety import summarize_log_value


class SurfaceController:
    """Handle surface/state mutations and render-tree lifecycle."""

    def __init__(self, window: Any) -> None:
        """Bind to window renderer, caches, and store integration points."""
        self.window = window

    def _mark_widget_index_dirty(self) -> None:
        marker = getattr(self.window, "_mark_widget_index_dirty", None)
        if callable(marker):
            marker()

    @staticmethod
    def _teardown_widget(widget: Any) -> None:
        if widget is None:
            return
        stop_animations(widget)
        if hasattr(widget, "setGraphicsEffect"):
            try:
                widget.setGraphicsEffect(None)
            except Exception:
                pass
        if hasattr(widget, "hide"):
            widget.hide()
        if hasattr(widget, "setParent"):
            widget.setParent(None)
        if hasattr(widget, "deleteLater"):
            widget.deleteLater()

    def prepare_for_app_switch(self) -> None:
        """Aggressively drop mounted UI trees when switching between apps."""
        pending_mounts = getattr(self.window, "_pending_surface_mounts", None)
        if isinstance(pending_mounts, dict):
            pending_mounts.clear()

        surface_roots = getattr(self.window, "_surface_roots", None)
        active_surfaces = list(surface_roots.keys()) if isinstance(surface_roots, dict) else []
        for surface_id in active_surfaces:
            if surface_id == "main":
                continue
            self.handle_delete_surface({"surfaceId": surface_id})

        self._clear_main_surface_container()

        surfaces = getattr(self.window, "surfaces", None)
        if isinstance(surfaces, dict):
            self.window.surfaces = {"main": {"components": {}, "data_model": {}}}
            background_tasks = getattr(self.window, "_background_tasks", None)
            if background_tasks is not None and hasattr(background_tasks, "surfaces"):
                background_tasks.surfaces = self.window.surfaces
            sync_surfaces = getattr(self.window, "_sync_surfaces_to_renderer", None)
            if callable(sync_surfaces):
                sync_surfaces()

    def handle_data_model_update(self, update: dict) -> None:
        """Merge data-model payload into the target surface-local model."""
        surface_id = update.get("surfaceId", "main")
        data = update.get("data", {})
        if isinstance(data, dict):
            surface = self.window.surfaces.setdefault(
                surface_id,
                {"components": {}, "data_model": {}},
            )
            current = surface.get("data_model")
            if not isinstance(current, dict):
                current = {}
                surface["data_model"] = current
            _deep_merge(current, data)
        self.window._debug(
            f"dataModelUpdate for surface {surface_id}, keys: {list(data.keys())}"
        )
        bindings = getattr(self.window, "bindings", None)
        if (
            bindings is not None
            and isinstance(data, dict)
            and hasattr(bindings, "handle_data_model_update")
            and bindings.handle_data_model_update(surface_id, data)
        ):
            return
        root_id = getattr(self.window, "_surface_roots", {}).get(surface_id)
        if root_id:
            self.render_tree(surface_id, root_id)

    def handle_delete_surface(self, update: dict) -> None:
        """Remove a surface and close dialogs associated with it."""
        surface_id = update.get("surfaceId")
        if not surface_id:
            return

        self.window._debug(f"deleteSurface for {surface_id}")

        if surface_id in self.window.surfaces:
            del self.window.surfaces[surface_id]
        self.window._pending_surface_mounts.pop(surface_id, None)
        surface_roots = getattr(self.window, "_surface_roots", None)
        if isinstance(surface_roots, dict):
            surface_roots.pop(surface_id, None)

        host = self.window._get_surface_host(surface_id)
        if host and host.layout():
            if surface_id == "drawer":
                self._animate_drawer_exit(host)
            else:
                self.clear_layout(cast(QVBoxLayout, host.layout()))
        self._mark_widget_index_dirty()

        active = self.window.renderer.active_dialogs.get(surface_id, {})
        to_remove = []
        for did, dialog in active.items():
            self._close_dialog(dialog)
            to_remove.append(did)

        for did in to_remove:
            del active[did]

        self.window._sync_surfaces_to_renderer()

    def handle_state_update(self, update: dict) -> None:
        """Apply state values and optionally trigger selective rerender."""
        values = update.get("values", {})
        scope = str(update.get("scope", "page"))
        if values:
            try:
                self.window.store.update(values, scope)
            except Exception as exc:
                print(
                    f"[SURFACE_TRACE] state_update_exception scope={scope!r} "
                    f"values={summarize_log_value(values)!r} error={exc!r}",
                    flush=True,
                )
                raise

        self.window._debug(f"stateUpdate received, keys: {list(values.keys())}")

        render_target = update.get("renderTarget") or update.get("componentId")
        if render_target:
            self.window._debug(f"Triggering selective re-render for {render_target}")
            self.rerender_component(render_target)

    def handle_state_patch(self, update: dict) -> None:
        """Apply one collection patch to page/global client store."""
        path = str(update.get("path") or update.get("key") or "").strip()
        action = str(update.get("action") or update.get("op") or "").strip()
        scope = str(update.get("scope", "page"))
        if not path or not action:
            return

        self.window.store.patch(path, action, update.get("value"), scope)
        self.window._debug(f"statePatch received, scope={scope}, path={path}, action={action}")

    def rerender_component(self, comp_id: str) -> None:
        """Rebuild only one component subtree after state changes."""
        rerender_component(
            self,
            comp_id,
            qscrollarea_cls=QScrollArea,
            qtabwidget_cls=QTabWidget,
            qsplitter_cls=QSplitter,
        )

    def handle_surface_update(self, update: dict) -> None:
        """Replace one surface model with the latest server snapshot."""
        surface_id = update.get("surfaceId", "main")
        components: dict[str, dict[str, Any]] = {}
        for comp in update.get("components", []):
            cid = comp.get("id")
            if cid:
                components[str(cid)] = comp

        self.window._startup_trace(
            "surface_update",
            surface_id=surface_id,
            component_count=len(components),
        )
        previous = self.window.surfaces.get(surface_id, {})
        data_model = previous.get("data_model", {}) if isinstance(previous, dict) else {}
        options = previous.get("options", {}) if isinstance(previous, dict) else {}
        self.window.surfaces[surface_id] = {
            "components": components,
            "data_model": data_model if isinstance(data_model, dict) else {},
            "options": options if isinstance(options, dict) else {},
        }

        self.window._sync_surfaces_to_renderer()
        self.window._debug(
            f"surfaceUpdate for {surface_id} completed. Total components: "
            f"{len(self.window.surfaces[surface_id]['components'])}"
        )

    def handle_begin_rendering(self, cmd: dict) -> None:
        """Entry point from protocol to render a surface root tree."""
        surface_id = cmd["surfaceId"]
        root_id = cmd["root"]
        options = cmd.get("options")
        if isinstance(options, dict):
            surface = self.window.surfaces.setdefault(
                surface_id,
                {"components": {}, "data_model": {}, "options": {}},
            )
            surface["options"] = dict(options)
        self.window._surface_roots[surface_id] = root_id
        self.window._debug(f"beginRendering triggered for {surface_id}, root={root_id}")
        self.window._startup_trace(
            "begin_rendering",
            surface_id=surface_id,
            root_id=root_id,
        )
        self.render_tree(surface_id, root_id)

    def render_tree(self, surface_id: str, root_id: str) -> None:
        """Clear current UI and mount the widget tree for `root_id`."""
        self.window._startup_trace(
            "render_tree_start",
            surface_id=surface_id,
            root_id=root_id,
        )
        try:
            render_tree(self, surface_id, root_id, slide_fn=slide, fade_in_fn=fade_in)
        except Exception as exc:
            print(
                f"[SURFACE_TRACE] render_tree_exception surface_id={surface_id!r} "
                f"root_id={root_id!r} error={exc!r}",
                flush=True,
            )
            raise
        if surface_id == "main":
            self.window._startup_trace_rendered_main = True
        self.window._startup_trace(
            "render_tree_done",
            surface_id=surface_id,
            root_id=root_id,
            size=f"{self.window.width()}x{self.window.height()}",
        )

    def _rerender_mounted_subsurfaces(self) -> None:
        rerender_mounted_subsurfaces(self)

    def _close_dialog(self, dialog: Any) -> None:
        if not hasattr(dialog, "close"):
            return
        if not hasattr(dialog, "pos"):
            dialog.close()
            return

        end_pos = dialog.pos()
        if isinstance(end_pos, QPoint):
            start_pos = QPoint(end_pos)
            end_pos = QPoint(end_pos)
            end_pos.setY(end_pos.y() - 24)
            slide(dialog, start=start_pos, end=end_pos, duration=180)
            fade_out(
                dialog,
                duration=180,
                start=1.0,
                end=0.0,
                hide_on_finish=False,
                finished=dialog.close,
            )
            return
        dialog.close()

    def _animate_drawer_exit(self, host: Any) -> None:
        animate_drawer_exit(self, host, slide_fn=slide, fade_out_fn=fade_out)

    def _clear_main_surface_container(self) -> None:
        """Fully detach the current main page widget tree before remounting."""
        self.clear_layout(self.window.ui_layout)

        ui_container = getattr(self.window, "ui_container", None)
        if ui_container is None or not hasattr(ui_container, "children"):
            return

        for child in list(ui_container.children()):
            if not isinstance(child, QWidget):
                continue
            if child is ui_container:
                continue
            self._teardown_widget(child)
        self.window._mark_widget_index_dirty()

    def clear_layout(self, layout: QVBoxLayout) -> None:
        """Delete all widgets/items in a Qt layout."""
        while layout.count():
            child = layout.takeAt(0)
            nested_layout = child.layout() if hasattr(child, "layout") else None
            if nested_layout is not None:
                self.clear_layout(cast(QVBoxLayout, nested_layout))
            w = child.widget()
            if w is not None:
                self._teardown_widget(w)
