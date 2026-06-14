from __future__ import annotations

import asyncio
import ipaddress
import socket
import subprocess
import threading
from typing import Any

from democrai.core.infrastructure.sandbox.os.windows import sandbox_host, winfwp
from democrai.core.platform.utils.debug import debug_os_sandbox_flow


_default_endpoint: str | None = None
_default_endpoint_lock = threading.Lock()


def _is_loopback_ip(host: str) -> bool:
    try:
        return ipaddress.ip_address(str(host).strip()).is_loopback
    except ValueError:
        return False


def _resolve_v4_allowed(endpoints: list[dict[str, Any]]) -> list[winfwp.AllowedEndpoint]:
    """Translate helper endpoint dicts to resolved IPv4 WFP allow entries.

    Loopback endpoints are dropped — ``apply_block_except`` always permits
    loopback. Hostnames are resolved to their IPv4 addresses (the proxy endpoint
    is already a loopback IP, so in practice this stays empty for deny/proxy; the
    resolution path exists for any future non-loopback allow targets).
    """
    allowed: list[winfwp.AllowedEndpoint] = []
    for endpoint in endpoints or []:
        host = str(endpoint.get("host") or "").strip()
        port = int(endpoint.get("port") or 0)
        protocol = str(endpoint.get("protocol") or "tcp").strip().lower()
        if not host or port <= 0:
            continue
        if _is_loopback_ip(host):
            continue
        try:
            infos = socket.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
        except socket.gaierror:
            continue
        for _family, _type, _proto, _canon, sockaddr in infos:
            ip = str(sockaddr[0])
            if _is_loopback_ip(ip):
                continue
            allowed.append(winfwp.AllowedEndpoint(host_ip=ip, port=port, protocol=protocol))
    # Dedup.
    return list(dict.fromkeys(allowed))


class WindowsHelperBackend:
    # Egress is now enforced at the OS level via WFP (FwpmFilterAdd0 at
    # ALE_AUTH_CONNECT), keyed on the sandboxed child's executable image path
    # (its ALE_APP_ID). This is the Windows analog of the Linux cgroup+iptables
    # helper and, unlike the in-process policy_guard, also catches ctypes/native
    # sockets and child subprocess egress.
    supports_pid_enforcement = True
    # Enforcement is applied inside the Windows spawn path (keyed on the real
    # low-integrity child pid / its app-id), not from the generic launcher apply
    # hook — that hook's pid is the intermediate wrapper, which would be the
    # wrong target. The launcher checks this flag and skips its own apply.
    applies_enforcement_at_spawn = True

    def __init__(self) -> None:
        self._engine: winfwp.WfpEngine | None = None
        self._lock = threading.Lock()
        # pid -> identity, so clear() can target a child whose image path can no
        # longer be queried (it may have already exited).
        self._pid_identity: dict[int, winfwp.WfpIdentity] = {}
        # identity key -> set of live pids sharing it (children launched from the
        # same sandbox-host executable share one filter set; ref-count so one
        # child's teardown does not clear another's enforcement).
        self._identity_pids: dict[str, set[int]] = {}

    def ensure_ready(self) -> None:
        # Fail closed: WFP write access requires elevation. Without it we must NOT
        # silently run unconfined — the provider's capabilities reflect this so a
        # deny/proxy launch is refused rather than left open.
        if not winfwp.is_process_elevated():
            raise RuntimeError("windows_network_enforcement_requires_elevation")
        with self._lock:
            if self._engine is None:
                engine = winfwp.WfpEngine()
                engine.open()
                self._engine = engine

    def default_socket_path(self) -> str:
        # CPython on Windows has no AF_UNIX: the helper listens on loopback
        # TCP. The port is OS-assigned (bind to 0) and cached per process so
        # every caller in this process sees the same endpoint — the same
        # stability the per-pid unix socket path provided. Children inherit it
        # via OS_SANDBOX_HELPER_SOCKET_ENV before the helper starts.
        global _default_endpoint
        with _default_endpoint_lock:
            if _default_endpoint is None:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.bind(("127.0.0.1", 0))
                    port = probe.getsockname()[1]
                _default_endpoint = f"tcp:127.0.0.1:{port}"
            return _default_endpoint

    def can_autostart_directly(self) -> bool:
        return True

    def spawn_helper_process(self, command: list[str], popen_kwargs: dict[str, Any]):
        # The helper must be elevated (WFP write needs admin). Launch it via
        # ShellExecuteEx "runas" → the Windows UAC consent dialog. runas cannot
        # redirect stdio or pass an env block, so we rely on cwd=app_root for
        # `python -m <pkg>` resolution and the elevated helper logs to its own
        # file; close the prepared log handle to avoid leaking it.
        from democrai.core.infrastructure.sandbox.os.windows import elevation
        from democrai.core.infrastructure.sandbox.os.windows.sandbox_host import (
            real_interpreter,
        )

        command = list(command)
        if command:
            # The helper is privileged infrastructure: it hosts the egress CONNECT
            # proxy and must reach allowlisted upstreams. It must run from the REAL
            # interpreter, never the sandbox-host exe — otherwise its app-id matches
            # the WFP block-except-loopback filter and the proxy's own upstream
            # connect is denied (WinError 5 → media-proxy 502). In the relaunched
            # Low core sys.executable IS the sandbox-host exe, so de-host command[0].
            command[0] = real_interpreter(command[0])

        proc = elevation.spawn_elevated_process(command, cwd=popen_kwargs.get("cwd"))
        proc.args = list(command)
        log_handle = popen_kwargs.get("stdout")
        if hasattr(log_handle, "close"):
            try:
                log_handle.close()
            except Exception:
                pass
        return proc

    def autostart_interactive(self, runtime_mode: str | None) -> bool:
        return False

    def autostart_stdin(self, *, strategy: str, interactive: bool) -> Any:
        return subprocess.DEVNULL

    def validate_client_and_target_pid(
        self,
        *,
        writer: asyncio.StreamWriter,
        requested_pid: int | None,
        parent_pid: int | None,
    ) -> int | None:
        if requested_pid is None:
            return None
        target = int(requested_pid)
        # Lineage guard (defense-in-depth atop the HMAC client token): only pids
        # in the launching app's process tree may be targeted. Best-effort —
        # toolhelp parent pids can be reused — so a query failure does not hard
        # fail; the token remains the primary boundary.
        if parent_pid is not None:
            try:
                if not winfwp.is_descendant_pid(target, int(parent_pid)):
                    raise RuntimeError(
                        f"os_sandbox_helper_target_pid_not_descendant:{target}:{int(parent_pid)}"
                    )
            except OSError:
                pass
        return target

    def apply(self, endpoints: list[dict[str, Any]], *, pid: int | None) -> None:
        if pid is None:
            raise RuntimeError("os_sandbox_helper_apply_requires_pid:win32")
        self.ensure_ready()
        assert self._engine is not None
        image_path = winfwp.process_image_path(int(pid))
        # WFP keys filters on the process image (app-id). A real sandboxed child
        # is launched from a per-child sandbox-host exe, so its image ends in
        # *-democrai-sandbox.exe. Any OTHER image is a SHARED interpreter
        # (base/venv) also used by trusted infrastructure — the elevated helper
        # that hosts the egress CONNECT proxy, the desktop UI. Keying a block on
        # it would confine them too (the cause of the media-proxy WinError 5 /
        # 502). Only ever enforce genuine sandbox-host identities.
        if not sandbox_host.is_sandbox_host(image_path):
            debug_os_sandbox_flow(
                "windows.apply_skipped_non_host_image", pid=int(pid), image=image_path
            )
            return
        identity = winfwp.WfpIdentity(kind="app_id", value=image_path)
        identity_key = f"{identity.kind}:{identity.value}".lower()
        allowed = _resolve_v4_allowed(endpoints)
        with self._lock:
            self._pid_identity[int(pid)] = identity
            live = self._identity_pids.setdefault(identity_key, set())
            first_for_identity = not live
            live.add(int(pid))
            # One filter set per identity: install only for the first child that
            # uses this sandbox-host image; later children share it.
            if first_for_identity:
                self._engine.apply_block_except(identity, allowed=allowed, loopback=True)

    def clear(self, *, pid: int | None) -> None:
        if pid is None or self._engine is None:
            return
        with self._lock:
            identity = self._pid_identity.pop(int(pid), None)
            if identity is None:
                return
            identity_key = f"{identity.kind}:{identity.value}".lower()
            live = self._identity_pids.get(identity_key)
            if live is not None:
                live.discard(int(pid))
                if live:
                    # Other children still share this identity's filters.
                    return
                self._identity_pids.pop(identity_key, None)
            self._engine.clear_identity(identity)
