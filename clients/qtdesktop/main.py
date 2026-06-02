from __future__ import annotations
import sys
import os
import argparse
import time
from typing import Any, Dict, List
import shiboken6
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
)
from PySide6.QtCore import Signal, Slot

from .ui.window_actions import center_window
from .ui.controllers.style import load_app_stylesheet
from .ui.composition import (
    init_window_core_state,
    init_window_ui,
    init_window_runtime_objects,
    init_window_services,
    update_global_surface_hosts_geometry,
    wire_window_signals,
)
from .runtime.signals import install_shutdown_signal_handlers
from .runtime.lifecycle import shutdown_window_runtime
from .ui.devtools import setup_devtools
from .logging import get_logger

DESKTOP_DEBUG = os.getenv("DEMOCRAI_DESKTOP_DEBUG", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
DEVTOOLS_ENABLED = os.getenv("DEMOCRAI_UI_DEVTOOLS", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def excepthook(exc_type, exc_value, exc_traceback):
    """Global exception hook to catch and log uncaught exceptions."""
    import traceback

    print("!!! UNCAUGHT EXCEPTION !!!", file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = excepthook


class MainWindow(QMainWindow):
    """Qt shell for the desktop client.

    This class owns the window, creates controllers, wires Qt signals, and
    delegates business logic to controllers/services.
    """

    action_triggered = Signal(
        str, dict, str, str
    )  # name, context, surface_id, component_id

    def __init__(self, host: str = "localhost", port: int = 8000):
        """Build the window and wire all controllers.

        window = MainWindow(host="localhost", port=8000)
        """
        super().__init__()
        self.host = host
        self.port = port
        init_window_core_state(self, debug_enabled=DESKTOP_DEBUG)
        self._startup_trace(
            "window_core_state_ready",
            jwt_present=bool(getattr(self, "jwt", "")),
            session_key=bool(getattr(self, "session_key", "")),
        )

        self.setWindowTitle("Democr.ai")
        # Smaller initial size for login/setup
        self.resize(500, 700)
        self.center_window()
        self._startup_trace("initial_geometry", size=f"{self.width()}x{self.height()}")

        init_window_ui(self)
        init_window_runtime_objects(self)
        init_window_services(self)
        wire_window_signals(self)
        self._devtools = setup_devtools(self, enabled=DEVTOOLS_ENABLED)
        self._startup_trace("desktop_services_ready")

        self._session.connect_to_core()

    def _sync_surfaces_to_renderer(self) -> None:
        """Push the latest surfaces map into the renderer and invalidate cache."""
        self.renderer.surfaces = self.surfaces
        self._mark_widget_index_dirty()

    def _debug(self, message: str) -> None:
        """Log a debug message, honoring `DEMOCRAI_DESKTOP_DEBUG`."""
        get_logger().debug(message)

    def _warn(self, message: str) -> None:
        """Log a warning message to app logger (or stdout fallback)."""
        get_logger().warning(message)

    def _error(self, message: str) -> None:
        """Log an error message to app logger (or stdout fallback)."""
        get_logger().error(message)

    def _startup_trace(self, event: str, **payload: Any) -> None:
        """Emit focused startup diagnostics for the desktop handshake."""
        if not bool(getattr(self, "_startup_trace_enabled", False)):
            return
        started_at = float(getattr(self, "_startup_trace_started_at", 0.0) or 0.0)
        elapsed_ms = int((time.monotonic() - started_at) * 1000) if started_at else 0
        details = " ".join(
            f"{key}={value!r}"
            for key, value in sorted(payload.items())
            if value is not None
        )
        suffix = f" {details}" if details else ""
        print(f"[DesktopStartup +{elapsed_ms}ms] {event}{suffix}", flush=True)

    @Slot()
    def _on_ready_read(self) -> None:
        """Qt socket callback: delegate inbound byte parsing to `InboundController`."""
        self._inbound.on_ready_read()

    def center_window(self):
        """Center the window on the current primary screen."""
        center_window(self)

    def _mark_widget_index_dirty(self) -> None:
        """Mark the widget index cache as stale."""
        self._widget_index_dirty = True

    def _rebuild_widget_index_from_window(self) -> None:
        """Re-index widgets by objectName and refresh input widgets cache."""
        if not self._widget_index_dirty:
            return
        widget_index: Dict[str, QWidget] = {}
        input_widgets: List[QWidget] = []
        for widget in self.findChildren(QWidget):
            if widget is None or not shiboken6.isValid(widget):
                continue
            obj_name = widget.objectName()
            if obj_name and obj_name != "unknown" and obj_name not in widget_index:
                widget_index[obj_name] = widget
            if bool(widget.property("is_input")):
                input_widgets.append(widget)
        self._widget_index = widget_index
        self._input_widgets_cache = input_widgets
        self._widget_index_dirty = False

    def _get_widget_by_id(self, comp_id: str) -> QWidget | None:
        """Resolve a component id to a QWidget using cache + Qt fallback lookup."""
        if not comp_id:
            return None
        self._rebuild_widget_index_from_window()
        widget = self._widget_index.get(comp_id)
        if widget is not None and shiboken6.isValid(widget):
            return widget
        self._widget_index.pop(comp_id, None)
        # Fallback for transient widgets not yet indexed.
        widget = self.findChild(QWidget, comp_id)
        if widget is not None and shiboken6.isValid(widget):
            self._widget_index[comp_id] = widget
            return widget
        return widget

    def _get_surface_host(self, surface_id: str) -> QWidget | None:
        global_hosts = getattr(self, "_global_surface_hosts", None)
        if isinstance(global_hosts, dict):
            host = global_hosts.get(surface_id)
            if host is not None:
                try:
                    if shiboken6.isValid(host):
                        return host
                except Exception:
                    return host
                global_hosts.pop(surface_id, None)

        self._rebuild_widget_index_from_window()
        for comp_id, widget in list(self._widget_index.items()):
            if widget is None or not shiboken6.isValid(widget):
                self._widget_index.pop(comp_id, None)
                continue
            if widget.property("surface_host_id") == surface_id:
                return widget
        for widget in self.findChildren(QWidget):
            if widget is None or not shiboken6.isValid(widget):
                continue
            if widget.property("surface_host_id") == surface_id:
                self._widget_index[widget.objectName()] = widget
                return widget
        return None

    def _update_surface_host_geometry(self) -> None:
        update_global_surface_hosts_geometry(self)

    def resizeEvent(self, event) -> None:
        self._update_surface_host_geometry()
        super().resizeEvent(event)

    def closeEvent(self, event):
        """Stop timers/socket deterministically before letting Qt close the window."""
        shutdown_window_runtime(self)
        super().closeEvent(event)


def run_gui(host: str = "localhost", port: int = 8000) -> int:
    """Application entrypoint for the desktop UI process.

    raise SystemExit(run_gui(host="localhost", port=8000))
    """
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    install_shutdown_signal_handlers(app)

    try:
        css = load_app_stylesheet(DESKTOP_DEBUG)
        if css:
            instance = QApplication.instance()
            if instance:
                instance.setStyleSheet(css)  # type: ignore
                if DESKTOP_DEBUG:
                    print("Stylesheet loaded")
    except Exception as e:
        get_logger().warning(f"Failed to load stylesheet: {e}")

    window = MainWindow(host=host, port=port)
    window.show()  # Use show instead of showMaximized to respect initial resize
    window._startup_trace("window_shown", size=f"{window.width()}x{window.height()}")
    try:
        return app.exec()
    except KeyboardInterrupt:
        app.quit()
        return 130


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    raise SystemExit(run_gui(host=args.host, port=args.port))
