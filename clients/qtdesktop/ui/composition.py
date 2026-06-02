from __future__ import annotations

import os
import time
import uuid
from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtNetwork import QLocalSocket, QTcpSocket
from PySide6.QtWidgets import QApplication, QComboBox, QTabBar, QToolButton, QVBoxLayout, QSizePolicy, QWidget

from ..auth.token_store import JwtTokenStore
from ..state import Binder, Store
from ..tasks.background_tasks import BackgroundTaskTracker
from .bindings import BindingController
from .controllers.notifications import NotificationController
from .controllers.action import ActionController
from .controllers.action_locks import ActionLockController
from .controllers.agent_ui import AgentUIBridge
from .controllers.inbound import InboundController
from .controllers.media import MediaController
from .controllers.property_updates import PropertyUpdateController
from .controllers.session import SessionController
from .controllers.style import StyleController
from .controllers.surfaces import SurfaceController
from .notifications import ToastViewport
from .ui_renderer import UIRenderer


class WheelSelectionGuard(QObject):
    """Prevent accidental value changes while scrolling over selects and tabs."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if event.type() != QEvent.Type.Wheel:
            return False
        if isinstance(obj, QComboBox):
            view = obj.view()
            if view is not None and view.isVisible():
                return False
            event.ignore()
            return True
        if isinstance(obj, QTabBar):
            event.ignore()
            return True
        return False


def init_window_core_state(window: Any, *, debug_enabled: bool) -> None:
    """Initialize base state/services required by desktop runtime."""
    window.debug_enabled = debug_enabled
    window._startup_trace_enabled = False
    window._startup_trace_started_at = time.monotonic()
    window._startup_trace_inbound_count = 0
    window._startup_trace_rendered_main = False
    window.token_store = JwtTokenStore()
    window.jwt = window.token_store.load_token(on_error=window._error)
    window.session_key = uuid.uuid4().hex
    window.surfaces = {"main": {"components": {}, "data_model": {}}}
    window._surface_roots = {}
    window._pending_surface_mounts = {}
    window._bg_tasks = {}
    window._widget_index = {}
    window._input_widgets_cache = []
    window._widget_index_dirty = True
    window._ui_generation = 0
    window._pending_nav_generation_bump = False


def init_window_ui(window: Any) -> None:
    """Build core window widgets and top-level layouts."""
    window.central_widget = QWidget(window)
    window.setCentralWidget(window.central_widget)

    window.main_layout = QVBoxLayout(window.central_widget)
    window.main_layout.setContentsMargins(0, 0, 0, 0)
    window.main_layout.setSpacing(0)

    window.ui_container = QWidget(window.central_widget)
    window.ui_container.setObjectName("ui_container")
    window.ui_container.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )

    window.ui_layout = QVBoxLayout(window.ui_container)
    window.ui_layout.setContentsMargins(0, 0, 0, 0)
    window.ui_layout.setSpacing(0)

    window.main_layout.addWidget(window.ui_container, 1)

    window._global_surface_hosts = {}
    drawer_host = QWidget(window.central_widget)
    if hasattr(drawer_host, "setObjectName"):
        drawer_host.setObjectName("app_global_drawer_host")
    if hasattr(drawer_host, "setProperty"):
        drawer_host.setProperty("surface_host_id", "drawer")
    if hasattr(drawer_host, "setAttribute"):
        drawer_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    if hasattr(drawer_host, "setSizePolicy"):
        drawer_host.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )
    _DRAWER_CLOSE_BTN_SIZE = 26
    _DRAWER_CLOSE_BTN_MARGIN = 10
    try:
        _DRAWER_CONTENT_MARGIN_TOP = max(
            0,
            int(os.getenv("DEMOCRAI_UI_DRAWER_CONTENT_MARGIN_TOP", "12")),
        )
    except Exception:
        _DRAWER_CONTENT_MARGIN_TOP = 12
    _DRAWER_CONTENT_TOP = (
        _DRAWER_CLOSE_BTN_SIZE
        + _DRAWER_CLOSE_BTN_MARGIN * 2
        + _DRAWER_CONTENT_MARGIN_TOP
    )

    drawer_layout = QVBoxLayout(drawer_host)
    drawer_layout.setContentsMargins(0, _DRAWER_CONTENT_TOP, 0, 0)
    drawer_layout.setSpacing(0)

    drawer_close_btn = QToolButton(drawer_host)
    drawer_close_btn.setObjectName("drawer_close_btn")
    drawer_close_btn.setText("✕")
    drawer_close_btn.setFixedSize(_DRAWER_CLOSE_BTN_SIZE, _DRAWER_CLOSE_BTN_SIZE)
    drawer_close_btn.setProperty("ui_role", "drawer_close_btn")
    drawer_close_btn.setProperty("size_px", _DRAWER_CLOSE_BTN_SIZE)
    drawer_close_btn.move(_DRAWER_CLOSE_BTN_MARGIN, _DRAWER_CLOSE_BTN_MARGIN)
    drawer_close_btn.raise_()
    window._drawer_close_btn = drawer_close_btn

    if hasattr(drawer_host, "hide"):
        drawer_host.hide()
    window._global_surface_hosts["drawer"] = drawer_host

    approval_feed_host = QWidget(window.central_widget)
    if hasattr(approval_feed_host, "setObjectName"):
        approval_feed_host.setObjectName("app_external_access_feed_host")
    if hasattr(approval_feed_host, "setProperty"):
        approval_feed_host.setProperty("surface_host_id", "approval_feed")
    if hasattr(approval_feed_host, "setAttribute"):
        approval_feed_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    if hasattr(approval_feed_host, "setSizePolicy"):
        approval_feed_host.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

    approval_feed_layout = QVBoxLayout(approval_feed_host)
    approval_feed_layout.setContentsMargins(0, 0, 0, 0)
    approval_feed_layout.setSpacing(0)
    if hasattr(approval_feed_host, "hide"):
        approval_feed_host.hide()
    window._global_surface_hosts["approval_feed"] = approval_feed_host

    try:
        window._global_drawer_width = max(
            280,
            int(os.getenv("DEMOCRAI_UI_DRAWER_WIDTH", "720")),
        )
    except Exception:
        window._global_drawer_width = 720
    try:
        window._drawer_scroll_top_margin = max(
            0,
            int(os.getenv("DEMOCRAI_UI_DRAWER_SCROLL_TOP_MARGIN", "40")),
        )
    except Exception:
        window._drawer_scroll_top_margin = 40
    try:
        window._external_access_feed_width = max(
            320,
            int(os.getenv("DEMOCRAI_UI_APPROVAL_FEED_WIDTH", "440")),
        )
    except Exception:
        window._external_access_feed_width = 440
    try:
        window._external_access_feed_height = max(
            140,
            int(os.getenv("DEMOCRAI_UI_APPROVAL_FEED_HEIGHT", "240")),
        )
    except Exception:
        window._external_access_feed_height = 240
    try:
        window._external_access_feed_margin = max(
            0,
            int(os.getenv("DEMOCRAI_UI_APPROVAL_FEED_MARGIN", "16")),
        )
    except Exception:
        window._external_access_feed_margin = 16
    try:
        window._external_access_feed_compact_width = max(
            220,
            int(os.getenv("DEMOCRAI_UI_APPROVAL_FEED_COMPACT_WIDTH", "300")),
        )
    except Exception:
        window._external_access_feed_compact_width = 300
    try:
        window._external_access_feed_compact_height = max(
            52,
            int(os.getenv("DEMOCRAI_UI_APPROVAL_FEED_COMPACT_HEIGHT", "64")),
        )
    except Exception:
        window._external_access_feed_compact_height = 64
    update_global_surface_hosts_geometry(window)

    try:
        window.toast_viewport = ToastViewport(window.central_widget)
    except Exception:
        window.toast_viewport = None


def init_window_runtime_objects(window: Any) -> None:
    """Create timers, socket and inbound update buffers."""
    window.reconnect_timer = QTimer(window)
    window.reconnect_timer.setInterval(1000)

    endpoint = str(os.getenv("DEMOCRAI_IPC_ENDPOINT", "")).strip()
    if not endpoint:
        raise RuntimeError("DEMOCRAI_IPC_ENDPOINT is required")
    window._ipc_endpoint = endpoint
    window.client = QTcpSocket(parent=window) if endpoint.startswith("tcp://") else QLocalSocket(parent=window)
    window._buf = bytearray()
    window._inbound_queue = []
    window._inbound_seq = 0
    window._inbound_max_per_tick = max(
        1,
        int(os.getenv("DEMOCRAI_UI_INBOUND_MAX_PER_TICK", "120")),
    )
    window._inbound_warn_threshold = max(
        1,
        int(os.getenv("DEMOCRAI_UI_INBOUND_WARN_THRESHOLD", "2000")),
    )
    window._inbound_enqueued_total = 0
    window._inbound_processed_total = 0
    window._inbound_max_depth_seen = 0
    window._inbound_metrics_window_enqueued = 0
    window._inbound_metrics_window_processed = 0
    window._inbound_metrics_last_ts = time.monotonic()
    window._inbound_last_warn_ts = 0.0

    window._inbound_drain_timer = QTimer(window)
    window._inbound_drain_timer.setSingleShot(True)
    window._inbound_drain_timer.setInterval(0)

    window._pending_property_updates = {}
    window._property_flush_timer = QTimer(window)
    window._property_flush_timer.setSingleShot(True)
    window._property_flush_timer.setInterval(16)


def init_window_services(window: Any) -> None:
    """Create state/binder, renderer and all domain controllers."""
    app = QApplication.instance()
    if app is not None and not hasattr(window, "_wheel_selection_guard"):
        window._wheel_selection_guard = WheelSelectionGuard(window)
        app.installEventFilter(window._wheel_selection_guard)

    window.store = Store(parent=window)
    if window.store.get("/system/client/theme", None, "global") is None:
        window.store.set("/system/client/theme", "dark", "global")
    window.binder = Binder(window.store, window)
    window.bindings = BindingController(window)

    window.renderer = UIRenderer(parent=window, store=window.store)
    window.renderer.bindings = window.bindings
    window.renderer.host = window.host
    window.renderer.port = window.port

    window._background_tasks = BackgroundTaskTracker(
        task_store=window._bg_tasks,
        surfaces=window.surfaces,
        debug=window._debug,
        warn=window._warn,
        on_surfaces_changed=window._sync_surfaces_to_renderer,
        store=window.store,
    )
    window._session = SessionController(window)
    window._session.apply_auth_claims(window.jwt)
    window._action_locks = ActionLockController(window)
    window._action = ActionController(window)
    window._media = MediaController(window)
    window._style = StyleController(window, debug_enabled=window.debug_enabled)
    window._property_updates = PropertyUpdateController(window)
    window._agent_ui = AgentUIBridge(window, window._property_updates)
    window._surfaces = SurfaceController(window)
    window._notifications = NotificationController(
        window,
        background_tasks=window._background_tasks,
    )
    window._inbound = InboundController(window, window._session)


def wire_window_signals(window: Any) -> None:
    """Wire Qt signals across socket, timers and controllers."""
    window.reconnect_timer.timeout.connect(window._session.connect_to_core)
    window.client.connected.connect(window._session.on_connected)
    window.client.connected.connect(window._notifications.start_polling)
    window.client.errorOccurred.connect(window._session.on_error)
    window.client.errorOccurred.connect(window._notifications.stop_polling)
    window.client.disconnected.connect(window._session.on_disconnected)
    window.client.disconnected.connect(window._notifications.stop_polling)
    window.client.readyRead.connect(window._on_ready_read)
    window._inbound_drain_timer.timeout.connect(window._inbound.drain)
    window._property_flush_timer.timeout.connect(window._property_updates.flush)

    window.renderer.action_triggered.connect(window._action.send_action)
    window.action_triggered.connect(window._action.send_action)

    drawer_close_btn = getattr(window, "_drawer_close_btn", None)
    if drawer_close_btn is not None:
        drawer_close_btn.clicked.connect(
            lambda: window._surfaces.handle_delete_surface({"surfaceId": "drawer"})
        )


def update_global_surface_hosts_geometry(window: Any) -> None:
    """Keep fixed-position global surface hosts aligned to the window geometry."""
    hosts = getattr(window, "_global_surface_hosts", None)
    central_widget = getattr(window, "central_widget", None)
    if not isinstance(hosts, dict) or central_widget is None:
        return

    drawer_host = hosts.get("drawer")
    if not all(hasattr(central_widget, name) for name in ("width", "height")):
        return
    parent_width = max(0, int(central_widget.width()))
    parent_height = max(0, int(central_widget.height()))

    if drawer_host is not None and hasattr(drawer_host, "setGeometry"):
        drawer_surface = getattr(window, "surfaces", {}).get("drawer", {})
        drawer_options = drawer_surface.get("options", {}) if isinstance(drawer_surface, dict) else {}
        position = str(drawer_options.get("position") or "right").strip().lower()
        if position not in {"right", "left", "top", "bottom"}:
            position = "right"
        size = drawer_options.get("dim", getattr(window, "_global_drawer_width", 420))
        try:
            size = max(120, int(size))
        except Exception:
            size = getattr(window, "_global_drawer_width", 420)
        if position in {"left", "right"}:
            host_width = min(max(280, int(size)), parent_width)
            x = max(0, parent_width - host_width) if position == "right" else 0
            drawer_host.setGeometry(x, 0, host_width, parent_height)
        else:
            host_height = min(max(120, int(size)), parent_height)
            y = max(0, parent_height - host_height) if position == "bottom" else 0
            drawer_host.setGeometry(0, y, parent_width, host_height)
        if hasattr(drawer_host, "raise_"):
            drawer_host.raise_()
        drawer_close_btn = getattr(window, "_drawer_close_btn", None)
        if drawer_close_btn is not None and hasattr(drawer_close_btn, "raise_"):
            drawer_close_btn.raise_()

    approval_feed_host = hosts.get("approval_feed")
    if approval_feed_host is not None and hasattr(approval_feed_host, "setGeometry"):
        margin = getattr(window, "_external_access_feed_margin", 16)
        width = getattr(window, "_external_access_feed_width", 440)
        height = getattr(window, "_external_access_feed_height", 240)
        try:
            margin = max(0, int(margin))
        except Exception:
            margin = 16
        try:
            width = max(320, int(width))
        except Exception:
            width = 440
        try:
            height = max(140, int(height))
        except Exception:
            height = 240

        max_width = max(0, parent_width - (margin * 2))
        max_height = max(0, parent_height - (margin * 2))
        host_width = min(width, max_width)
        host_height = min(height, max_height)
        x = max(margin, parent_width - host_width - margin)
        y = max(margin, parent_height - host_height - margin)
        approval_feed_host.setGeometry(x, y, host_width, host_height)
        if hasattr(approval_feed_host, "raise_"):
            approval_feed_host.raise_()

    toast_viewport = getattr(window, "toast_viewport", None)
    if toast_viewport is not None and hasattr(toast_viewport, "raise_"):
        toast_viewport.raise_()
