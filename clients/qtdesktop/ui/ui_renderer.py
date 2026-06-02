from __future__ import annotations

import os
from typing import Any, Optional, Dict

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog, QWidget

from ..logging import get_logger
from ..state import Store
from .renderers.base import BaseRenderer
from .client_tags import build_default_client_tag_registry
from .controllers.renderer_engine import RendererEngine

DESKTOP_DEBUG = os.getenv("DEMOCRAI_DESKTOP_DEBUG", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


class UIRenderer(QObject):
    """Facade over renderer discovery and widget construction.

    MainWindow delegates component rendering to this class, which in turn
    delegates heavy logic to `RendererEngine`.
    """
    action_triggered = Signal(
        str, dict, str, str
    )  # name, context, surface_id, component_id

    def __init__(self, parent: QObject | None = None, store: Store | None = None):
        """Initialize renderer registry and load renderer modules."""
        super().__init__(parent)
        self.registry: dict[str, BaseRenderer] = {}
        self.user_permissions: list[str] = []
        self.user_role = "Guest"
        self.is_connected = False
        self.surfaces: dict = {}
        self._bg_tasks: dict = {}  # task_id -> task info
        self.active_dialogs: Dict[
            str, Dict[str, QDialog]
        ] = {}  # surface -> {id: dialog}
        self.host: str = "localhost"
        self.port: int = 8000
        self.store: Store = store or Store(parent=self)
        self.bindings = getattr(parent, "bindings", None)
        self.client_tag_registry = build_default_client_tag_registry()
        self.engine = RendererEngine(self)
        self.load_renderers()

    def _debug(self, message: str) -> None:
        """Write debug diagnostics for renderer internals."""
        get_logger().debug(message)

    def _error(self, message: str) -> None:
        """Write renderer errors to app logger (or stdout fallback)."""
        get_logger().error(message)

    def load_renderers(self) -> None:
        """Discover and register all component renderers."""
        self.engine.load_renderers()

    def resolve_bindings(
        self,
        data: Any,
        item: Optional[dict] = None,
        property_name: Optional[str] = None,
    ) -> Any:
        """Resolve `$state`, `$global`, `$item` and templated bindings."""
        return self.engine.resolve_bindings(data, item, property_name)

    def render_component(
        self,
        component_data: dict,
        surface_id: str,
        app_instance=None,
        item: Optional[dict] = None,
    ):
        """Render one component definition into a QWidget."""
        return self.engine.render_component(component_data, surface_id, app_instance, item)

    def build_widget(
        self,
        surface_id: str,
        surfaces: dict,
        comp_id: str | None = None,
        comp_def: dict | None = None,
        item: Optional[dict] = None,
        app_instance: Any = None,
        seen_dialogs: Optional[set[str]] = None,
    ):
        """Build a widget tree node (component + optional children)."""
        return self.engine.build_widget(
            surface_id=surface_id,
            surfaces=surfaces,
            comp_id=comp_id,
            comp_def=comp_def,
            item=item,
            app_instance=app_instance,
            seen_dialogs=seen_dialogs,
        )

    def populate_children(
        self,
        widget: QWidget,
        comp_props: dict,
        raw_props: dict,
        resolved_comp_def: dict,
        surface_id: str,
        surfaces: dict,
        item: Optional[dict],
        app_instance: Any,
        seen_dialogs: set[str] | None,
        renderer: Any,
        comp_id: str,
    ):
        """Append/render child components into an existing parent widget."""
        self.engine.populate_children(
            widget=widget,
            comp_props=comp_props,
            raw_props=raw_props,
            resolved_comp_def=resolved_comp_def,
            surface_id=surface_id,
            surfaces=surfaces,
            item=item,
            app_instance=app_instance,
            seen_dialogs=seen_dialogs,
            renderer=renderer,
            comp_id=comp_id,
        )
