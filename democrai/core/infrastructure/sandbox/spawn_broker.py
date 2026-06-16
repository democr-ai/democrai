from __future__ import annotations

import array
import json
import os
import secrets
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from democrai.core.infrastructure.sandbox.os.launch_policy import (
    NETWORK_PROXY,
    SandboxLaunchPolicy,
    policy_from_payload,
)


SPAWN_BROKER_SOCKET_ENV = "DEMOCRAI_SANDBOX_SPAWN_BROKER_SOCKET"
SPAWN_BROKER_TOKEN_ENV = "DEMOCRAI_SANDBOX_SPAWN_BROKER_TOKEN"

_MAX_MESSAGE_BYTES = 8 * 1024 * 1024
_CMSG_FD_BYTES = 64 * array.array("i").itemsize
# Upper bound on how long a broker handler waits for a client to send its
# request before giving up (a silent/partial peer must not pin the thread).
_CLIENT_READ_TIMEOUT_SECONDS = 30.0


class SpawnBroker:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(32)
        if sys.platform == "win32":
            # CPython on Windows does not expose AF_UNIX; loopback TCP with the
            # mandatory request token mirrors the orchestrator transport choice.
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Windows SO_REUSEADDR lets a second socket steal a bound port;
            # SO_EXCLUSIVEADDRUSE forbids it, so no other local process can
            # hijack or share this control-plane loopback port.
            try:
                self._server.setsockopt(
                    socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
                )
            except (OSError, AttributeError):
                pass
            self._server.bind(("127.0.0.1", 0))
            self.socket_path = f"tcp:127.0.0.1:{self._server.getsockname()[1]}"
        else:
            self.socket_path = _new_socket_path()
            self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server.bind(str(self.socket_path))
        self._server.listen(64)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._next_handle = 1
        self._processes: dict[int, subprocess.Popen[Any]] = {}
        self._proxy_sessions: dict[int, str] = {}
        self._token_policies: dict[str, SandboxLaunchPolicy | None] = {self.token: None}
        self._thread = threading.Thread(
            target=self._serve,
            name="democrai-spawn-broker",
            daemon=True,
        )

    def start(self) -> "SpawnBroker":
        self._thread.start()
        return self

    def env(self) -> dict[str, str]:
        return {
            SPAWN_BROKER_SOCKET_ENV: str(self.socket_path),
            SPAWN_BROKER_TOKEN_ENV: self.token,
        }

    def close(self) -> None:
        self._stop.set()
        try:
            self._server.close()
        except OSError:
            pass
        try:
            client = _connect_broker_endpoint(str(self.socket_path), timeout=0.1)
            client.close()
        except OSError:
            pass
        self._thread.join(timeout=1.0)
        with self._lock:
            processes = list(self._processes.values())
            proxy_sessions = list(self._proxy_sessions.values())
            self._processes.clear()
            self._proxy_sessions.clear()
        for process in processes:
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
        for session_id in proxy_sessions:
            _stop_broker_proxy_session(session_id)
        if not str(self.socket_path).startswith("tcp:"):
            try:
                Path(str(self.socket_path)).unlink()
            except OSError:
                pass

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _addr = self._server.accept()
            except OSError:
                break
            threading.Thread(
                target=self._handle_connection,
                args=(conn,),
                name="democrai-spawn-broker-client",
                daemon=True,
            ).start()

    def _handle_connection(self, conn: socket.socket) -> None:
        fds: list[int] = []
        with conn:
            try:
                # Bound only the request read: a client that connects and never
                # (or partially) sends must not pin this handler thread forever.
                # The dispatch/spawn and response are left unbounded.
                conn.settimeout(_CLIENT_READ_TIMEOUT_SECONDS)
                request, fds = _recv_message(conn)
                conn.settimeout(None)
                if not fds:
                    fds = self._materialize_windows_handles(request)
                response = self._dispatch(request, fds, conn)
            except Exception as exc:
                response = {"ok": False, "error": str(exc)}
            try:
                _send_message(conn, response)
            except OSError:
                pass
            finally:
                for fd in fds:
                    _close_fd(fd)

    def _materialize_windows_handles(self, request: Any) -> list[int]:
        """Windows replacement for SCM_RIGHTS: duplicate client pipe handles.

        The client embeds its pid and raw handle values in the request; after
        the token pre-check we duplicate them into this process so the rest of
        the dispatch path keeps working on local fds.
        """
        if sys.platform != "win32" or not isinstance(request, dict):
            return []
        handles = [int(item) for item in (request.get("handles") or [])]
        if not handles:
            return []
        if str(request.get("token") or "") not in self._token_policies:
            raise RuntimeError("spawn_broker_token_invalid")
        client_pid = int(request.get("client_pid") or 0)
        if client_pid <= 0:
            raise RuntimeError("spawn_broker_client_pid_required")
        return _duplicate_client_handles(client_pid, handles)

    def _dispatch(
        self,
        request: dict[str, Any],
        fds: list[int],
        conn: socket.socket,
    ) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise RuntimeError("spawn_broker_request_invalid")
        token = str(request.get("token") or "")
        if token not in self._token_policies:
            raise RuntimeError("spawn_broker_token_invalid")
        _validate_peer_uid(conn)
        action = str(request.get("action") or "").strip()
        if action == "spawn":
            return self._spawn(request, fds, parent_policy=self._token_policies[token])
        if action == "poll":
            return self._poll(_handle_id(request))
        if action == "wait":
            return self._wait(_handle_id(request), request.get("timeout"))
        if action == "terminate":
            return self._signal(_handle_id(request), kill=False)
        if action == "kill":
            return self._signal(_handle_id(request), kill=True)
        if action == "cleanup":
            return self._cleanup(_handle_id(request))
        raise RuntimeError(f"spawn_broker_action_unknown:{action}")

    def _spawn(
        self,
        request: dict[str, Any],
        fds: list[int],
        *,
        parent_policy: SandboxLaunchPolicy | None,
    ) -> dict[str, Any]:
        policy = policy_from_payload(dict(request.get("policy") or {}))
        _validate_child_policy(parent_policy, policy)
        child_token = secrets.token_urlsafe(32)
        child_env = dict(policy.env or {})
        child_env[SPAWN_BROKER_SOCKET_ENV] = str(self.socket_path)
        child_env[SPAWN_BROKER_TOKEN_ENV] = child_token
        proxy_session_id = ""
        stdio = dict(request.get("stdio") or {})
        stdin = _stdio_value(stdio.get("stdin"), fds)
        stdout = _stdio_value(stdio.get("stdout"), fds)
        stderr = _stdio_value(stdio.get("stderr"), fds)
        if policy.network_mode == NETWORK_PROXY:
            proxy_session_id, proxy_url = _start_broker_proxy_session(policy)
            _set_proxy_env(child_env, proxy_url)
        policy = replace(policy, env=child_env)
        from democrai.core.infrastructure.sandbox.os.factory import (
            get_core_launch_strategy,
        )

        from democrai.core.infrastructure.sandbox.process_guard import (
            process_guard_bypass_context,
        )

        try:
            with process_guard_bypass_context():
                process = get_core_launch_strategy().spawn(
                    policy,
                    stdin=stdin,
                    stdout=stdout,
                    stderr=stderr,
                )
        except Exception:
            _stop_broker_proxy_session(proxy_session_id)
            raise
        with self._lock:
            handle_id = self._next_handle
            self._next_handle += 1
            self._processes[handle_id] = process
            if proxy_session_id:
                self._proxy_sessions[handle_id] = proxy_session_id
            self._token_policies[child_token] = policy
        return {"ok": True, "handle": handle_id, "pid": int(process.pid)}

    def _process(self, handle_id: int) -> subprocess.Popen[Any]:
        with self._lock:
            process = self._processes.get(int(handle_id))
        if process is None:
            raise RuntimeError(f"spawn_broker_process_unknown:{handle_id}")
        return process

    def _poll(self, handle_id: int) -> dict[str, Any]:
        return {"ok": True, "returncode": self._process(handle_id).poll()}

    def _wait(self, handle_id: int, timeout: Any) -> dict[str, Any]:
        process = self._process(handle_id)
        try:
            return {"ok": True, "returncode": process.wait(timeout=_optional_timeout(timeout))}
        except subprocess.TimeoutExpired:
            raise TimeoutError("spawn_broker_wait_timeout")

    def _signal(self, handle_id: int, *, kill: bool) -> dict[str, Any]:
        process = self._process(handle_id)
        if kill:
            process.kill()
        else:
            process.terminate()
        return {"ok": True, "returncode": process.poll()}

    def _cleanup(self, handle_id: int) -> dict[str, Any]:
        with self._lock:
            process = self._processes.pop(int(handle_id), None)
            proxy_session_id = self._proxy_sessions.pop(int(handle_id), "")
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        _stop_broker_proxy_session(proxy_session_id)
        return {"ok": True}


class BrokeredPopen:
    def __init__(
        self,
        *,
        handle: int,
        pid: int,
        command: list[str],
        stdin,
        stdout,
        stderr,
        text: bool | None,
    ) -> None:
        self._handle = int(handle)
        self.args = list(command)
        self.pid = int(pid)
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.text_mode = bool(text)
        self.returncode: int | None = None

    def poll(self) -> int | None:
        response = _broker_request({"action": "poll", "handle": self._handle})
        self.returncode = response.get("returncode")
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        try:
            response = _broker_request(
                {"action": "wait", "handle": self._handle, "timeout": timeout}
            )
        except RuntimeError as exc:
            if str(exc) == "spawn_broker_wait_timeout":
                raise subprocess.TimeoutExpired(self.args, timeout) from exc
            raise
        self.returncode = int(response.get("returncode") or 0)
        return self.returncode

    def terminate(self) -> None:
        response = _broker_request({"action": "terminate", "handle": self._handle})
        self.returncode = response.get("returncode")

    def kill(self) -> None:
        response = _broker_request({"action": "kill", "handle": self._handle})
        self.returncode = response.get("returncode")

    def communicate(self, input: Any = None, timeout: float | None = None):
        if input is not None and self.stdin is not None:
            self.stdin.write(input)
        if self.stdin is not None:
            try:
                self.stdin.close()
            except OSError:
                pass
        stdout_holder: dict[str, Any] = {}
        stderr_holder: dict[str, Any] = {}
        threads = []
        if self.stdout is not None:
            threads.append(
                threading.Thread(
                    target=lambda: stdout_holder.setdefault("value", self.stdout.read()),
                    daemon=True,
                )
            )
        if self.stderr is not None:
            threads.append(
                threading.Thread(
                    target=lambda: stderr_holder.setdefault("value", self.stderr.read()),
                    daemon=True,
                )
            )
        for thread in threads:
            thread.start()
        try:
            self.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                self.kill()
            except Exception:
                pass
            raise
        for thread in threads:
            thread.join(timeout=1.0)
        return stdout_holder.get("value"), stderr_holder.get("value")

    def cleanup(self) -> None:
        try:
            _broker_request({"action": "cleanup", "handle": self._handle})
        except Exception:
            pass

    def __del__(self) -> None:
        self.cleanup()


def start_spawn_broker() -> SpawnBroker:
    return SpawnBroker().start()


def broker_env(broker: SpawnBroker | None) -> dict[str, str]:
    return broker.env() if broker is not None else {}


def broker_available() -> bool:
    return bool(
        str(os.environ.get(SPAWN_BROKER_SOCKET_ENV) or "").strip()
        and str(os.environ.get(SPAWN_BROKER_TOKEN_ENV) or "").strip()
    )


def strip_broker_env(env: dict[str, str]) -> dict[str, str]:
    resolved = dict(env)
    resolved.pop(SPAWN_BROKER_SOCKET_ENV, None)
    resolved.pop(SPAWN_BROKER_TOKEN_ENV, None)
    return resolved


def popen_via_broker(
    policy: SandboxLaunchPolicy,
    *,
    command: list[str],
    stdin: Any = None,
    stdout: Any = None,
    stderr: Any = None,
    text: bool | None = None,
) -> BrokeredPopen:
    stdio, fds, close_after_send, parent_streams = _prepare_stdio(
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        text=text,
    )
    try:
        response = _broker_request(
            {
                "action": "spawn",
                "policy": policy.to_dict(),
                "stdio": stdio,
            },
            fds=fds,
        )
        return BrokeredPopen(
            handle=int(response["handle"]),
            pid=int(response["pid"]),
            command=command,
            stdin=parent_streams.get("stdin"),
            stdout=parent_streams.get("stdout"),
            stderr=parent_streams.get("stderr"),
            text=text,
        )
    finally:
        for fd in close_after_send:
            _close_fd(fd)


def _prepare_stdio(
    *,
    stdin: Any,
    stdout: Any,
    stderr: Any,
    text: bool | None,
) -> tuple[dict[str, Any], list[int], list[int], dict[str, Any]]:
    fds: list[int] = []
    close_after_send: list[int] = []
    parent: dict[str, Any] = {}
    specs: dict[str, Any] = {}

    if stdin == subprocess.PIPE:
        read_fd, write_fd = os.pipe()
        specs["stdin"] = _fd_spec(fds, close_after_send, read_fd)
        parent["stdin"] = _open_parent_stream(write_fd, "w", text)
    elif stdin == subprocess.DEVNULL:
        specs["stdin"] = {"kind": "devnull_read"}
    elif isinstance(stdin, int):
        specs["stdin"] = _fd_spec(fds, close_after_send, stdin, close_after_send=False)
    else:
        specs["stdin"] = {"kind": "none"}

    if stdout == subprocess.PIPE:
        read_fd, write_fd = os.pipe()
        specs["stdout"] = _fd_spec(fds, close_after_send, write_fd)
        parent["stdout"] = _open_parent_stream(read_fd, "r", text)
    elif stdout == subprocess.DEVNULL:
        specs["stdout"] = {"kind": "devnull_write"}
    elif isinstance(stdout, int):
        specs["stdout"] = _fd_spec(fds, close_after_send, stdout, close_after_send=False)
    else:
        specs["stdout"] = {"kind": "none"}

    if stderr == subprocess.PIPE:
        read_fd, write_fd = os.pipe()
        specs["stderr"] = _fd_spec(fds, close_after_send, write_fd)
        parent["stderr"] = _open_parent_stream(read_fd, "r", text)
    elif stderr == subprocess.STDOUT:
        specs["stderr"] = {"kind": "stdout"}
    elif stderr == subprocess.DEVNULL:
        specs["stderr"] = {"kind": "devnull_write"}
    elif isinstance(stderr, int):
        specs["stderr"] = _fd_spec(fds, close_after_send, stderr, close_after_send=False)
    else:
        specs["stderr"] = {"kind": "none"}

    return specs, fds, close_after_send, parent


def _fd_spec(
    fds: list[int],
    close_fds: list[int],
    fd: int,
    *,
    close_after_send: bool = True,
) -> dict[str, Any]:
    fds.append(int(fd))
    if close_after_send:
        close_fds.append(int(fd))
    return {"kind": "fd", "index": len(fds) - 1, "close_after_send": close_after_send}


def _open_parent_stream(fd: int, mode: str, text: bool | None):
    if text:
        return os.fdopen(fd, mode, encoding="utf-8", buffering=1)
    return os.fdopen(fd, mode + "b", buffering=0)


def _broker_request(payload: dict[str, Any], *, fds: list[int] | None = None) -> dict[str, Any]:
    request = dict(payload)
    request["token"] = str(os.environ.get(SPAWN_BROKER_TOKEN_ENV) or "")
    socket_path = str(os.environ.get(SPAWN_BROKER_SOCKET_ENV) or "").strip()
    if not socket_path:
        raise RuntimeError("spawn_broker_socket_missing")
    send_fds = tuple(fds or ())
    if send_fds and sys.platform == "win32":
        import msvcrt

        request["handles"] = [int(msvcrt.get_osfhandle(int(fd))) for fd in send_fds]
        request["client_pid"] = int(os.getpid())
        send_fds = ()
    with _connect_broker_endpoint(socket_path) as client:
        _send_message(client, request, fds=send_fds)
        response, _response_fds = _recv_message(client)
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error") or "spawn_broker_request_failed"))
    return response


def _send_message(
    sock: socket.socket,
    payload: dict[str, Any],
    *,
    fds: tuple[int, ...] = (),
) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    frame = struct.pack("!I", len(body)) + body
    if not fds:
        sock.sendall(frame)
        return
    if sys.platform == "win32":
        raise RuntimeError("spawn_broker_fd_passing_unsupported_on_windows")
    ancdata = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))]
    sock.sendmsg([frame], ancdata)


def _recv_message(sock: socket.socket) -> tuple[dict[str, Any], list[int]]:
    if sys.platform == "win32":
        return _recv_message_plain(sock), []
    chunks: list[bytes] = []
    fds: list[int] = []
    expected: int | None = None
    while expected is None or sum(len(chunk) for chunk in chunks) < expected + 4:
        data, ancdata, _flags, _addr = sock.recvmsg(_MAX_MESSAGE_BYTES, _CMSG_FD_BYTES)
        if not data:
            break
        chunks.append(data)
        for level, ctype, cdata in ancdata:
            if level == socket.SOL_SOCKET and ctype == socket.SCM_RIGHTS:
                arr = array.array("i")
                arr.frombytes(cdata[: len(cdata) - (len(cdata) % arr.itemsize)])
                fds.extend(int(fd) for fd in arr)
        joined = b"".join(chunks)
        if expected is None and len(joined) >= 4:
            expected = struct.unpack("!I", joined[:4])[0]
            if expected > _MAX_MESSAGE_BYTES:
                raise RuntimeError("spawn_broker_message_too_large")
    joined = b"".join(chunks)
    if len(joined) < 4:
        raise RuntimeError("spawn_broker_message_truncated")
    size = struct.unpack("!I", joined[:4])[0]
    body = joined[4 : 4 + size]
    return json.loads(body.decode("utf-8")), fds


def _stdio_value(spec: Any, fds: list[int]):
    if not isinstance(spec, dict):
        return None
    kind = str(spec.get("kind") or "none")
    if kind == "fd":
        return int(fds[int(spec.get("index"))])
    if kind == "devnull_read":
        return subprocess.DEVNULL
    if kind == "devnull_write":
        return subprocess.DEVNULL
    if kind == "stdout":
        return subprocess.STDOUT
    return None


def _validate_child_policy(
    parent: SandboxLaunchPolicy | None,
    child: SandboxLaunchPolicy,
) -> None:
    if parent is None:
        return
    if not _network_within_parent(parent, child):
        raise RuntimeError("spawn_broker_child_network_policy_exceeds_parent")
    for access in child.filesystem_access:
        if not _filesystem_access_within_parent(parent, access.operation, access.target):
            raise RuntimeError(
                f"spawn_broker_child_filesystem_policy_exceeds_parent:{access.operation}:{access.target}"
            )


def _network_within_parent(
    parent: SandboxLaunchPolicy,
    child: SandboxLaunchPolicy,
) -> bool:
    if parent.network_mode == child.network_mode:
        if child.network_mode != "proxy":
            return True
        parent_targets = {str(item.target) for item in parent.network_endpoints}
        return all(str(item.target) in parent_targets for item in child.network_endpoints)
    if parent.network_mode == "allow_all":
        return True
    if child.network_mode == "deny":
        return True
    return False


def _filesystem_access_within_parent(
    parent: SandboxLaunchPolicy,
    operation: str,
    target: str,
) -> bool:
    for access in parent.filesystem_access:
        if not _operation_covers(access.operation, operation):
            continue
        if _path_covers(access.target, target):
            return True
    return False


def _operation_covers(parent_operation: str, child_operation: str) -> bool:
    parent = str(parent_operation or "").strip()
    child = str(child_operation or "").strip()
    if parent == child:
        return True
    if parent in {"create", "modify", "delete"} and child == "read":
        return True
    if parent == "read" and child == "execute":
        return True
    return False


def _path_covers(parent_target: str, child_target: str) -> bool:
    for parent in _path_compare_variants(parent_target):
        for child in _path_compare_variants(child_target):
            if child == parent or child.startswith(parent + os.sep):
                return True
    return False


def _path_compare_variants(path: str) -> tuple[str, ...]:
    raw = str(path or "").strip()
    variants: list[str] = []
    try:
        variants.append(os.path.normpath(os.path.abspath(os.path.expanduser(raw))))
    except Exception:
        variants.append(raw)
    try:
        variants.append(os.path.normpath(os.path.realpath(os.path.expanduser(raw))))
    except Exception:
        pass
    return tuple(dict.fromkeys(item for item in variants if item))


def _start_broker_proxy_session(policy: SandboxLaunchPolicy) -> tuple[str, str]:
    from democrai.core.runtime.foundation.app import app_ctx
    from democrai.core.infrastructure.sandbox.os.base import _network_endpoint_from_target
    from democrai.core.infrastructure.sandbox.os.helper import (
        start_application_network_proxy_session_with_helper,
    )
    from democrai.core.infrastructure.sandbox.os.models import (
        ApplicationNetworkAllowlist,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    endpoints = [
        endpoint
        for endpoint in (
            _network_endpoint_from_target(item) for item in policy.network_endpoints
        )
        if endpoint is not None
    ]
    if not endpoints:
        raise RuntimeError("spawn_broker_proxy_endpoints_required")
    config = getattr(app_ctx(), "config", None)
    with process_guard_bypass_context():
        session = start_application_network_proxy_session_with_helper(
            ApplicationNetworkAllowlist(endpoints=endpoints),
            config=config,
        )
    session_id = str(session.get("session_id") or "").strip()
    proxy_url = str(session.get("proxy_url") or "").strip()
    if not session_id or not proxy_url:
        raise RuntimeError("spawn_broker_proxy_session_invalid")
    return session_id, proxy_url


def _stop_broker_proxy_session(session_id: str) -> None:
    resolved = str(session_id or "").strip()
    if not resolved:
        return
    try:
        from democrai.core.runtime.foundation.app import app_ctx
        from democrai.core.infrastructure.sandbox.os.helper import (
            stop_application_network_proxy_session_with_helper,
        )
        from democrai.core.infrastructure.sandbox.process_guard import (
            process_guard_bypass_context,
        )

        config = getattr(app_ctx(), "config", None)
        with process_guard_bypass_context():
            stop_application_network_proxy_session_with_helper(resolved, config=config)
    except Exception:
        pass


def _set_proxy_env(env: dict[str, str], proxy_url: str) -> None:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "WS_PROXY",
        "WSS_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "ws_proxy",
        "wss_proxy",
    ):
        env[key] = str(proxy_url)
    env["NO_PROXY"] = "127.0.0.1,localhost,::1"
    env["no_proxy"] = "127.0.0.1,localhost,::1"


def _handle_id(request: dict[str, Any]) -> int:
    return int(request.get("handle") or 0)


def _optional_timeout(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _recv_message_plain(sock: socket.socket) -> dict[str, Any]:
    buffer = b""
    while len(buffer) < 4:
        data = sock.recv(65536)
        if not data:
            raise RuntimeError("spawn_broker_message_truncated")
        buffer += data
    size = struct.unpack("!I", buffer[:4])[0]
    if size > _MAX_MESSAGE_BYTES:
        raise RuntimeError("spawn_broker_message_too_large")
    while len(buffer) < 4 + size:
        data = sock.recv(65536)
        if not data:
            raise RuntimeError("spawn_broker_message_truncated")
        buffer += data
    return json.loads(buffer[4 : 4 + size].decode("utf-8"))


def _connect_broker_endpoint(endpoint: str, *, timeout: float | None = None) -> socket.socket:
    resolved = str(endpoint or "").strip()
    if resolved.startswith("tcp:"):
        host, _, port = resolved[len("tcp:") :].rpartition(":")
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if timeout is not None:
            client.settimeout(timeout)
        client.connect((host or "127.0.0.1", int(port)))
        return client
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    if timeout is not None:
        client.settimeout(timeout)
    client.connect(resolved)
    return client


def _duplicate_client_handles(client_pid: int, handles: list[int]) -> list[int]:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    PROCESS_DUP_HANDLE = 0x0040
    DUPLICATE_SAME_ACCESS = 0x0002
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = wintypes.HANDLE
    source = kernel32.OpenProcess(PROCESS_DUP_HANDLE, False, int(client_pid))
    if not source:
        raise RuntimeError(f"spawn_broker_client_process_unavailable:{client_pid}")
    current_process = wintypes.HANDLE(-1)  # GetCurrentProcess() pseudo-handle
    fds: list[int] = []
    try:
        for handle in handles:
            target = wintypes.HANDLE()
            if not kernel32.DuplicateHandle(
                wintypes.HANDLE(source),
                wintypes.HANDLE(int(handle)),
                current_process,
                ctypes.byref(target),
                0,
                False,
                DUPLICATE_SAME_ACCESS,
            ):
                raise ctypes.WinError()
            fds.append(msvcrt.open_osfhandle(int(target.value), 0))
    except Exception:
        for fd in fds:
            _close_fd(fd)
        raise
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(source))
    return fds


def _new_socket_path() -> Path:
    return Path("/tmp") / f"dc-sb-{os.getpid()}-{secrets.token_hex(6)}.sock"


def _close_fd(fd: int) -> None:
    try:
        os.close(int(fd))
    except OSError:
        pass


def _validate_peer_uid(conn: socket.socket) -> None:
    # Deliberate local platform check: LOCAL_PEERCRED is a Darwin-only socket
    # option, not a per-OS strategy concern worth a backend method.
    if sys.platform != "darwin" or not hasattr(socket, "LOCAL_PEERCRED"):
        return
    raw = conn.getsockopt(0, socket.LOCAL_PEERCRED, struct.calcsize("3i"))
    if len(raw) < struct.calcsize("2i"):
        raise RuntimeError("spawn_broker_peer_credentials_invalid")
    _version, uid = struct.unpack("2i", raw[: struct.calcsize("2i")])
    if int(uid) != int(os.getuid()):
        raise RuntimeError(f"spawn_broker_invalid_client_uid:{uid}:{os.getuid()}")
