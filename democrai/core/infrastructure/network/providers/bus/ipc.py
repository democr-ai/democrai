from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
from urllib.parse import urlparse
from typing import Any, Callable, Dict, Optional

from democrai.core.infrastructure.network.contracts import BusProvider
from democrai.core.platform.utils.debug import debug_ipc_trace as _debug_ipc_trace
from democrai.core.runtime.foundation.app import app_ctx


class IpcBusProvider(BusProvider):
    """Local IPC bus backed by a Unix domain socket."""

    _socket_counter = 0

    def __init__(
        self,
        server_name: str,
        on_message: Optional[Callable[[Any, Dict[str, Any]], None]] = None,
        on_disconnect: Optional[Callable[[Any], None]] = None,
    ):
        self.server_name = server_name
        self._transport, self._bind_target, self.endpoint = self._resolve_endpoint(server_name)
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        self._server: socket.socket | None = None
        self._sockets: dict[int, socket.socket] = {}
        self._buffers: dict[int, bytearray] = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._accept_thread: threading.Thread | None = None

    @staticmethod
    def _resolve_endpoint(server_name: str) -> tuple[str, Any, str]:
        value = str(server_name or "").strip()
        if not value:
            raise RuntimeError("IPC server name is required")
        if value.startswith("tcp://"):
            parsed = urlparse(value)
            host = parsed.hostname or "127.0.0.1"
            port = int(parsed.port or 0)
            return "tcp", (host, port), f"tcp://{host}:{port}"
        if value.startswith("unix://"):
            path = value[len("unix://") :]
            return "unix", path, f"unix:{path}"
        if value.startswith("unix:"):
            path = value[len("unix:") :]
            return "unix", path, f"unix:{path}"
        if os.name == "nt":
            return "tcp", ("127.0.0.1", 0), "tcp://127.0.0.1:0"
        if os.path.isabs(value):
            return "unix", value, f"unix:{value}"
        path = os.path.join(tempfile.gettempdir(), value)
        return "unix", path, f"unix:{path}"

    def start(self) -> None:
        if self._transport == "unix":
            os.makedirs(os.path.dirname(str(self._bind_target)), exist_ok=True)
            try:
                os.unlink(str(self._bind_target))
            except FileNotFoundError:
                pass
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        else:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(self._bind_target)
            server.listen(128)
            server.settimeout(0.2)
            if self._transport == "tcp":
                host, port = server.getsockname()
                self._bind_target = (host, port)
                self.endpoint = f"tcp://{host}:{port}"
        except Exception:
            server.close()
            raise

        self._server = server
        self._stop_event.clear()
        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name=f"IpcBus:{os.path.basename(self.endpoint)}",
            daemon=True,
        )
        self._accept_thread.start()
        app_ctx().logger.info(
            f"[IpcBus] Listening on {self.server_name} (endpoint={self.endpoint})"
        )

    def stop(self) -> None:
        self._stop_event.set()
        server = self._server
        self._server = None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        with self._lock:
            sockets = list(self._sockets.items())
            self._sockets.clear()
            self._buffers.clear()
        for _, sock in sockets:
            try:
                sock.close()
            except OSError:
                pass
        if self._accept_thread is not None and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=1.0)
        self._accept_thread = None
        if self._transport == "unix":
            try:
                os.unlink(str(self._bind_target))
            except FileNotFoundError:
                pass
            except OSError:
                pass

    def send(self, client_id: Any, message: Dict[str, Any]) -> None:
        try:
            resolved_client_id = int(client_id)
        except (TypeError, ValueError):
            return
        with self._lock:
            sock = self._sockets.get(resolved_client_id)
        if sock is None:
            return
        _debug_ipc_trace(
            "send",
            client_id=resolved_client_id,
            keys=list(message.keys()),
            has_current_path="current_path" in message,
            has_surface_update="surfaceUpdate" in message,
            has_begin_rendering="beginRendering" in message,
            has_state_update="stateUpdate" in message,
            has_window_action="windowAction" in message,
        )
        payload = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            sock.sendall(payload)
        except OSError:
            self._drop_client(resolved_client_id, notify=True)

    def broadcast(self, message: Dict[str, Any]) -> None:
        with self._lock:
            client_ids = list(self._sockets.keys())
        for client_id in client_ids:
            self.send(client_id, message)

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            server = self._server
            if server is None:
                return
            try:
                sock, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            IpcBusProvider._socket_counter += 1
            client_id = IpcBusProvider._socket_counter
            with self._lock:
                self._sockets[client_id] = sock
                self._buffers[client_id] = bytearray()
            app_ctx().logger.debug(f"[IpcBus] New connection, assigned ID: {client_id}")
            threading.Thread(
                target=self._read_loop,
                args=(client_id, sock),
                name=f"IpcBusClient:{client_id}",
                daemon=True,
            ).start()

    def _read_loop(self, client_id: int, sock: socket.socket) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    chunk = sock.recv(65536)
                except OSError:
                    break
                if not chunk:
                    break
                self._handle_chunk(client_id, chunk)
        finally:
            self._drop_client(client_id, notify=True)

    def _handle_chunk(self, client_id: int, chunk: bytes) -> None:
        with self._lock:
            buf = self._buffers.get(client_id)
            if buf is None:
                return
            buf.extend(chunk)
            if len(buf) > 4 * 1024 * 1024:  # Limit buffer size to prevent memory issues
                buf.clear()
                app_ctx().logger.error(f"[IpcBus] Buffer overflow from client {client_id}, dropping connection")
                self._drop_client(client_id, notify=True)
                return
            lines: list[bytes] = []
            while True:
                nl = buf.find(b"\n")
                if nl < 0:
                    break
                line = bytes(buf[:nl])
                del buf[: nl + 1]
                if line:
                    lines.append(line)

        _err = 0
        for line in lines:
            try:
                msg = json.loads(line.decode("utf-8"))
            except Exception as exc:
                app_ctx().logger.error(f"[IpcBus] JSON decode error: {exc}")
                _err += 1
                if _err >= 5:  # Limit error logging
                    app_ctx().logger.error(f"[IpcBus] Too many JSON decode errors from client {client_id}")
                    self._drop_client(client_id, notify=True)
                    break
                continue
            if self.on_message:
                self.on_message(client_id, msg)

    def _drop_client(self, client_id: int, *, notify: bool) -> None:
        with self._lock:
            sock = self._sockets.pop(client_id, None)
            self._buffers.pop(client_id, None)
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if notify and self.on_disconnect:
            self.on_disconnect(client_id)
