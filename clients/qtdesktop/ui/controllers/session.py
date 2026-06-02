from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any
from urllib.parse import urlencode, urlparse

import shiboken6
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtNetwork import QAbstractSocket, QLocalSocket

from ...auth.claims import extract_token_expiry


TOKEN_REFRESH_LEAD_SECONDS = 60
TOKEN_REFRESH_RETRY_SECONDS = 30
TOKEN_REFRESH_FALLBACK_SECONDS = 300
TOKEN_REFRESH_MIN_DELAY_MS = 1000


def _page_identity(path: str | None) -> str:
    parsed = urlparse(str(path or ""))
    return parsed.path or "/"


class SessionController:
    """Manage connection/session lifecycle for the desktop client."""
    def __init__(self, window: Any) -> None:
        """Bind to window state and I/O objects used by session flows."""
        self.window = window
        self._token_refresh_timer: QTimer | None = None

    @staticmethod
    def _alive(obj: Any) -> bool:
        """Return True if a Qt object is still valid (not deleted)."""
        try:
            return obj is not None and shiboken6.isValid(obj)
        except Exception:
            return False

    def apply_auth_claims(self, token: str | None) -> None:
        """Mirror only a minimal authenticated/guest state into `UIRenderer`."""
        exp = extract_token_expiry(token) if token else None
        if token and self._is_token_expired(token):
            self.window.jwt = ""
            self.save_jwt("")
            token = ""
        self.window.renderer.user_role = "User" if token else "Guest"
        self.window.renderer.user_permissions = []
        if not token:
            store = getattr(self.window, "store", None)
            if store is not None and hasattr(store, "update"):
                store.update(
                    {
                        "/auth/role": "Guest",
                        "/auth/permissions": [],
                        "/auth/permissions_loaded": False,
                    },
                    "global",
                )
        self._schedule_token_refresh(token)

    def connect_to_core(self) -> None:
        """Attempt IPC connection when socket is disconnected."""
        client = getattr(self.window, "client", None)
        if not self._alive(client):
            self.window._startup_trace("connect_to_core_skipped", reason="client_not_alive")
            return
        try:
            if client.state() == self._unconnected_state(client):
                endpoint = str(getattr(self.window, "_ipc_endpoint", "") or "").strip()
                if not endpoint:
                    raise RuntimeError("DEMOCRAI_IPC_ENDPOINT is required")
                self.window._startup_trace(
                    "connect_to_core_attempt",
                    server_name=endpoint,
                )
                self._connect_client(client, endpoint)
            else:
                self.window._startup_trace(
                    "connect_to_core_skipped",
                    reason="socket_not_disconnected",
                    socket_state=int(client.state()),
                )
        except RuntimeError:
            # Ignore late callbacks during shutdown.
            self.window._startup_trace("connect_to_core_runtime_error")
            return

    @staticmethod
    def _unconnected_state(client: Any) -> Any:
        if hasattr(client, "connectToHost"):
            return QAbstractSocket.SocketState.UnconnectedState
        return QLocalSocket.LocalSocketState.UnconnectedState

    @staticmethod
    def _connect_client(client: Any, endpoint: str) -> None:
        if endpoint.startswith("tcp://"):
            parsed = urlparse(endpoint)
            client.connectToHost(parsed.hostname or "127.0.0.1", int(parsed.port or 0))
            return
        if endpoint.startswith("unix://"):
            endpoint = endpoint[len("unix://") :]
        elif endpoint.startswith("unix:"):
            endpoint = endpoint[len("unix:") :]
        client.connectToServer(endpoint)

    def on_connected(self) -> None:
        """Reset client-side surface state and send init/plugin bootstrap messages."""
        self.window._startup_trace(
            "socket_connected",
            jwt_present=bool(getattr(self.window, "jwt", "")),
        )
        self._schedule_token_refresh(getattr(self.window, "jwt", ""))
        self.refresh_current_view()

    def refresh_current_view(self, *, clear_page_scope: bool = False) -> None:
        """Reset local UI state and request a fresh render from the core runtime."""
        if not self._alive(self.window):
            self.window._startup_trace(
                "refresh_current_view_skipped",
                reason="window_not_alive",
                clear_page_scope=clear_page_scope,
            )
            return
        self.window._startup_trace(
            "refresh_current_view_start",
            clear_page_scope=clear_page_scope,
            current_path=self.window.store.get("/current_path", None, "global"),
        )
        self.window.renderer.is_connected = True
        reconnect_timer = getattr(self.window, "reconnect_timer", None)
        if self._alive(reconnect_timer):
            reconnect_timer.stop()
        if clear_page_scope:
            self.window.store.clear_scope("page")
            bindings = getattr(self.window, "bindings", None)
            if bindings is not None:
                bindings.on_page_scope_reset()
        media = getattr(self.window, "_media", None)
        if media is not None and hasattr(media, "clear_pending_requests"):
            media.clear_pending_requests()
        action_locks = getattr(self.window, "_action_locks", None)
        if action_locks is not None:
            action_locks.clear()
        pending_updates = getattr(self.window, "_pending_property_updates", None)
        if isinstance(pending_updates, dict):
            pending_updates.clear()
        flush_timer = getattr(self.window, "_property_flush_timer", None)
        if flush_timer is not None and hasattr(flush_timer, "isActive") and flush_timer.isActive():
            flush_timer.stop()
        surface_roots = getattr(self.window, "_surface_roots", None)
        if isinstance(surface_roots, dict):
            surface_roots.clear()
        pending_mounts = getattr(self.window, "_pending_surface_mounts", None)
        if isinstance(pending_mounts, dict):
            pending_mounts.clear()
        self.window.surfaces = {"main": {"components": {}, "data_model": {}}}
        self.window._background_tasks.surfaces = self.window.surfaces
        self.window._sync_surfaces_to_renderer()
        self.window._inbound_queue.clear()

        msg = {
            "type": "init",
            "jwt": self.window.jwt,
            "session_key": str(getattr(self.window, "session_key", "") or ""),
        }
        data = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
        client = getattr(self.window, "client", None)
        if not self._alive(client):
            self.window._startup_trace(
                "refresh_current_view_skipped",
                reason="client_not_alive",
            )
            return
        client.write(data)
        client.flush()
        self.window._startup_trace(
            "outbound_sent",
            message_type="init",
            jwt_present=bool(self.window.jwt),
        )

        msgplugins = {"userAction": {"name": "modulesList", "context": {}}}
        dataplugins = (json.dumps(msgplugins, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        client.write(dataplugins)
        client.flush()
        self.window._startup_trace("outbound_sent", message_type="modulesList")
        # Always request auth context: session can be valid even when local JWT
        # is empty/stale (e.g. cookie-backed resume or reconnect flows).
        self._request_client_auth_context()

    def on_disconnected(self) -> None:
        """Mark UI disconnected and arm reconnect timer."""
        if not self._alive(self.window):
            return
        self.window._startup_trace("socket_disconnected")
        self.window.renderer.is_connected = False
        if self._token_refresh_timer is not None:
            self._token_refresh_timer.stop()
        reconnect_timer = getattr(self.window, "reconnect_timer", None)
        if not self._alive(reconnect_timer):
            return
        try:
            if not reconnect_timer.isActive():
                reconnect_timer.start()
        except RuntimeError:
            # Timer can be deleted while processing disconnect signal.
            return

    def on_error(self, _error_code: Any) -> None:
        """Socket error callback; normalized as disconnection handling."""
        self.window._startup_trace("socket_error", error_code=str(_error_code))
        self.on_disconnected()

    def save_jwt(self, token: str) -> None:
        """Persist JWT token to disk via secure token store."""
        self.window.token_store.save_token(token, on_error=self.window._error)

    def update_identity_from_message(self, data: dict) -> None:
        """Apply JWT updates arriving from server messages."""
        token = data.get("jwt")
        if not isinstance(token, str):
            return
        if token != self.window.jwt:
            self.window.jwt = token
            self.save_jwt(token)
            self.apply_auth_claims(token)
            if token:
                self._request_client_auth_context()

    def update_current_path_from_message(self, data: dict) -> None:
        """Mirror server `current_path` into client store."""
        if "current_path" not in data:
            return

        cp = data["current_path"]
        if isinstance(cp, dict):
            app_name = cp.get("app_name", "dashboard")
            page_path = cp.get("page_path", "index")
            params = cp.get("params")
            query = urlencode(params) if isinstance(params, dict) and params else ""
            next_path = f"/{app_name}/{page_path}"
            if query:
                next_path = f"{next_path}?{query}"
        else:
            next_path = cp

        current_path = self.window.store.get("/current_path", None, "global")
        page_changed = _page_identity(next_path) != _page_identity(current_path)
        if isinstance(next_path, str) and next_path != current_path and page_changed:
            self.window.store.clear_scope("page")
            self.window.bindings.on_page_scope_reset()
            media = getattr(self.window, "_media", None)
            if media is not None and hasattr(media, "clear_pending_requests"):
                media.clear_pending_requests()
            pending_updates = getattr(self.window, "_pending_property_updates", None)
            if isinstance(pending_updates, dict):
                pending_updates.clear()
            flush_timer = getattr(self.window, "_property_flush_timer", None)
            if flush_timer is not None and hasattr(flush_timer, "isActive") and flush_timer.isActive():
                flush_timer.stop()
            surfaces = getattr(self.window, "_surfaces", None)
            if surfaces is not None and hasattr(surfaces, "prepare_for_app_switch"):
                current_app = (current_path or "").split("/")[1] if current_path else ""
                next_app = next_path.split("/")[1] if next_path else ""
                if current_app != next_app:
                    surfaces.prepare_for_app_switch()
        self.window.store.set("/current_path", next_path, "global")

    def _ensure_refresh_timer(self) -> QTimer | None:
        if self._token_refresh_timer is not None:
            return self._token_refresh_timer
        if QCoreApplication.instance() is None:
            return None
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self._request_token_refresh)
        self._token_refresh_timer = timer
        return timer

    def _start_refresh_timer(self, delay_ms: int) -> None:
        timer = self._ensure_refresh_timer()
        if timer is None:
            return
        timer.start(max(TOKEN_REFRESH_MIN_DELAY_MS, int(delay_ms)))

    def _schedule_token_refresh(self, token: str | None) -> None:
        timer = self._ensure_refresh_timer()
        if timer is None:
            return
        timer.stop()
        if not token:
            return

        now = int(time.time())
        exp = extract_token_expiry(token)
        if exp is None:
            delay_seconds = TOKEN_REFRESH_FALLBACK_SECONDS
        else:
            delay_seconds = max(1, exp - now - TOKEN_REFRESH_LEAD_SECONDS)
        self._start_refresh_timer(delay_seconds * 1000)

    def _request_token_refresh(self) -> None:
        token = getattr(self.window, "jwt", "") or ""
        if not isinstance(token, str) or not token:
            return
        if self._is_token_expired(token):
            self.window.jwt = ""
            self.save_jwt("")
            self.apply_auth_claims("")
            return
        client = getattr(self.window, "client", None)
        if not self._alive(client):
            self._start_refresh_timer(TOKEN_REFRESH_RETRY_SECONDS * 1000)
            return

        try:
            msg = {
                "request_id": str(uuid.uuid4()),
                "jwt": token,
                "userAction": {"name": "refresh_token", "context": {}},
            }
            data = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
            client.write(data)
            client.flush()
        except Exception:
            pass

        # Keep a retry armed; a new JWT from inbound messages will reschedule.
        self._start_refresh_timer(TOKEN_REFRESH_RETRY_SECONDS * 1000)

    def _request_client_auth_context(self) -> None:
        client = getattr(self.window, "client", None)
        if not self._alive(client):
            return
        try:
            token = getattr(self.window, "jwt", "") or ""
            msg = {
                "request_id": str(uuid.uuid4()),
                "jwt": token,
                "userAction": {"name": "load_client_auth_context", "context": {}},
            }
            data = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
            client.write(data)
            client.flush()
            self.window._startup_trace(
                "outbound_sent",
                message_type="load_client_auth_context",
                jwt_present=bool(token),
            )
        except Exception:
            pass

    @staticmethod
    def _is_token_expired(token: str) -> bool:
        exp = extract_token_expiry(token)
        if exp is None:
            return False
        return exp <= int(time.time())
