from __future__ import annotations

import asyncio
import hmac
import json
import os
import select
import socket
import struct
import threading
import time
from pathlib import Path
from typing import Any

from democrai.core.platform.utils.debug import debug_os_sandbox_flow

from .linux import (
    apply_application_network_endpoints,
    clear_application_network_allowlist,
    ensure_linux_network_enforcement_ready,
)
from .proxy import OsSandboxConnectProxy


def _socket_owner_ids() -> tuple[int, int] | None:
    elevated_uid = str(
        os.environ.get("SUDO_UID") or os.environ.get("PKEXEC_UID") or ""
    ).strip()
    elevated_gid = str(os.environ.get("SUDO_GID", "") or "").strip()
    if not elevated_uid:
        return None
    try:
        uid = int(elevated_uid)
        gid = int(elevated_gid or os.getgid())
        return uid, gid
    except Exception:
        return None


def _load_endpoints_from_policy_file(policy_file: str) -> list[dict[str, Any]]:
    path = Path(str(policy_file or "").strip()).expanduser().resolve()
    try:
        stat_result = path.stat()
    except Exception as exc:
        raise RuntimeError(f"os_sandbox_policy_stat_failed:{path}") from exc
    expected_uid = _expected_client_uid()
    if int(stat_result.st_uid) != int(expected_uid):
        raise RuntimeError(
            f"os_sandbox_policy_invalid_owner:{int(stat_result.st_uid)}:{int(expected_uid)}:{path}"
        )
    if int(stat_result.st_mode) & 0o022:
        raise RuntimeError(f"os_sandbox_policy_insecure_mode:{oct(int(stat_result.st_mode) & 0o777)}:{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("os_sandbox_policy_invalid_payload")
    raw_items = payload.get("endpoints")
    if not isinstance(raw_items, list):
        raise RuntimeError("os_sandbox_policy_missing_endpoints")
    endpoints: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        endpoints.append(
            {
                "host": str(item.get("host") or "").strip(),
                "port": int(item.get("port") or 0),
                "protocol": str(item.get("protocol") or "tcp").strip(),
                "source": str(item.get("source") or "").strip(),
                "purpose": str(item.get("purpose") or "").strip(),
            }
        )
    return endpoints


def _expected_client_uid() -> int:
    elevated_uid = str(
        os.environ.get("SUDO_UID") or os.environ.get("PKEXEC_UID") or ""
    ).strip()
    if elevated_uid:
        try:
            return int(elevated_uid)
        except Exception:
            pass
    return int(os.getuid())


def _peer_credentials(writer: asyncio.StreamWriter) -> tuple[int, int, int]:
    sock = writer.get_extra_info("socket")
    if sock is None:
        raise RuntimeError("os_sandbox_helper_missing_peer_socket")
    raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    pid, uid, gid = struct.unpack("3i", raw)
    return int(pid), int(uid), int(gid)


def _parent_pid_of(pid: int) -> int | None:
    try:
        raw = Path(f"/proc/{int(pid)}/status").read_text(encoding="utf-8")
    except Exception:
        return None
    for line in raw.splitlines():
        if not line.startswith("PPid:"):
            continue
        try:
            return int(str(line.split(":", 1)[1]).strip())
        except Exception:
            return None
    return None


def _is_same_or_descendant(pid: int, root_pid: int) -> bool:
    current = int(pid)
    root = int(root_pid)
    visited: set[int] = set()
    while current > 1 and current not in visited:
        if current == root:
            return True
        visited.add(current)
        parent = _parent_pid_of(current)
        if parent is None:
            return False
        current = parent
    return current == root


def _validate_client_and_target_pid(
    *,
    writer: asyncio.StreamWriter,
    requested_pid: int | None,
    parent_pid: int | None,
) -> int | None:
    peer_pid, peer_uid, _peer_gid = _peer_credentials(writer)
    expected_uid = _expected_client_uid()
    if peer_uid != expected_uid:
        raise RuntimeError(
            f"os_sandbox_helper_invalid_client_uid:{peer_uid}:{expected_uid}"
        )
    if parent_pid is not None and not _is_same_or_descendant(
        int(peer_pid),
        int(parent_pid),
    ):
        raise RuntimeError(
            f"os_sandbox_helper_invalid_client_pid:{peer_pid}:{int(parent_pid)}"
        )
    if requested_pid is None:
        return None
    resolved_pid = int(requested_pid)
    if parent_pid is not None and not _is_same_or_descendant(resolved_pid, int(parent_pid)):
        raise RuntimeError(
            f"os_sandbox_helper_invalid_target_pid:{resolved_pid}:{int(parent_pid)}"
        )
    return resolved_pid


def _validate_helper_token(payload: dict[str, Any], expected_token: str) -> None:
    expected = str(expected_token or "").strip()
    if not expected:
        raise RuntimeError("os_sandbox_helper_token_required")
    supplied = str(payload.get("token") or "").strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise RuntimeError("os_sandbox_helper_invalid_token")


def _parent_pid_is_alive(parent_pid: int) -> bool:
    try:
        os.kill(int(parent_pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _open_parent_pidfd(parent_pid: int | None) -> int | None:
    if not parent_pid or int(parent_pid) <= 1 or not hasattr(os, "pidfd_open"):
        return None
    try:
        return int(os.pidfd_open(int(parent_pid), 0))
    except Exception:
        return None


def _start_parent_watchdog(parent_pid: int | None) -> None:
    if not parent_pid or int(parent_pid) <= 1:
        return
    pidfd = _open_parent_pidfd(parent_pid)

    def watchdog() -> None:
        if pidfd is not None:
            poller = select.poll()
            poller.register(pidfd, select.POLLIN)
            poller.poll()
            try:
                os.close(pidfd)
            except Exception:
                pass
            debug_os_sandbox_flow(
                "helper.parent_gone_exit",
                parent_pid=int(parent_pid),
            )
            os._exit(0)
        while True:
            if not _parent_pid_is_alive(int(parent_pid)):
                debug_os_sandbox_flow(
                    "helper.parent_gone_exit",
                    parent_pid=int(parent_pid),
                )
                os._exit(0)
            time.sleep(1.0)

    thread = threading.Thread(
        target=watchdog,
        name="os-sandbox-helper-parent-watchdog",
        daemon=True,
    )
    thread.start()


def _start_policy_refresh_watchdog(
    *,
    policy_file: str,
    refresh_seconds: int,
    applied_pids: set[int],
    applied_pids_lock: threading.Lock,
) -> None:
    if int(refresh_seconds) <= 0:
        return

    def watchdog() -> None:
        while True:
            time.sleep(float(refresh_seconds))
            with applied_pids_lock:
                target_pids = sorted(applied_pids)
            if not target_pids:
                continue
            try:
                endpoints = _load_endpoints_from_policy_file(policy_file)
                for target_pid in target_pids:
                    if not _parent_pid_is_alive(int(target_pid)):
                        with applied_pids_lock:
                            applied_pids.discard(int(target_pid))
                        continue
                    apply_application_network_endpoints(endpoints, pid=int(target_pid))
                    debug_os_sandbox_flow(
                        "helper.periodic_refresh_applied",
                        policy_file=policy_file,
                        pid=int(target_pid),
                        endpoint_count=len(endpoints),
                        refresh_seconds=int(refresh_seconds),
                    )
            except Exception as exc:
                debug_os_sandbox_flow(
                    "helper.periodic_refresh_failed",
                    policy_file=policy_file,
                    pids=target_pids,
                    error=str(exc),
                )

    thread = threading.Thread(
        target=watchdog,
        name="os-sandbox-helper-policy-refresh",
        daemon=True,
    )
    thread.start()


async def _handle_helper_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    policy_file: str,
    parent_pid: int | None,
    applied_pids: set[int],
    applied_pids_lock: threading.Lock,
    proxy: OsSandboxConnectProxy,
    token: str,
) -> None:
    try:
        raw = await reader.readline()
        if not raw:
            return
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("os_sandbox_helper_invalid_payload")
        _validate_helper_token(payload, token)
        action = str(payload.get("action") or "").strip().lower()
        pid = _validate_client_and_target_pid(
            writer=writer,
            requested_pid=payload.get("pid"),
            parent_pid=parent_pid,
        )
        if action == "ping":
            ensure_linux_network_enforcement_ready()
            response = {"ok": True}
        elif action == "apply":
            endpoints = _load_endpoints_from_policy_file(policy_file)
            apply_application_network_endpoints(endpoints, pid=pid)
            if pid is not None:
                with applied_pids_lock:
                    applied_pids.add(int(pid))
            response = {"ok": True, "endpoint_count": len(endpoints)}
        elif action == "clear":
            clear_application_network_allowlist(pid=pid)
            with applied_pids_lock:
                if pid is None:
                    applied_pids.clear()
                else:
                    applied_pids.discard(int(pid))
            response = {"ok": True}
        elif action == "start_proxy_session":
            endpoints = payload.get("endpoints")
            if not isinstance(endpoints, list):
                raise RuntimeError("os_sandbox_helper_endpoints_must_be_list")
            await proxy.start()
            response = {
                "ok": True,
                **proxy.create_session(endpoints=endpoints),
            }
        elif action == "update_proxy_session":
            endpoints = payload.get("endpoints")
            if not isinstance(endpoints, list):
                raise RuntimeError("os_sandbox_helper_endpoints_must_be_list")
            await proxy.start()
            response = {
                "ok": True,
                **proxy.update_session(
                    str(payload.get("session_id") or ""),
                    endpoints=endpoints,
                ),
            }
        elif action == "stop_proxy_session":
            proxy.stop_session(str(payload.get("session_id") or ""))
            response = {"ok": True}
        else:
            response = {"ok": False, "error": f"os_sandbox_helper_unknown_action:{action}"}
    except Exception as exc:
        response = {"ok": False, "error": str(exc)}
        debug_os_sandbox_flow("helper.server_error", error=str(exc))
    writer.write((json.dumps(response) + "\n").encode("utf-8"))
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def run_os_sandbox_helper_server(
    socket_path: str,
    *,
    policy_file: str,
    refresh_seconds: int = 60,
    parent_pid: int | None = None,
    token: str = "",
) -> int:
    resolved_socket_path = Path(str(socket_path or "").strip()).expanduser().resolve()
    resolved_socket_path.parent.mkdir(parents=True, exist_ok=True)
    if resolved_socket_path.exists():
        resolved_socket_path.unlink()
    _start_parent_watchdog(parent_pid)
    applied_pids: set[int] = set()
    applied_pids_lock = threading.Lock()
    proxy = OsSandboxConnectProxy()
    _start_policy_refresh_watchdog(
        policy_file=policy_file,
        refresh_seconds=int(refresh_seconds),
        applied_pids=applied_pids,
        applied_pids_lock=applied_pids_lock,
    )
    debug_os_sandbox_flow(
        "helper.server_start",
        socket_path=str(resolved_socket_path),
        policy_file=str(Path(policy_file).expanduser().resolve()),
        refresh_seconds=int(refresh_seconds),
    )
    server = await asyncio.start_unix_server(
        lambda reader, writer: _handle_helper_client(
            reader,
            writer,
            policy_file=policy_file,
            parent_pid=parent_pid,
            applied_pids=applied_pids,
            applied_pids_lock=applied_pids_lock,
            proxy=proxy,
            token=token,
        ),
        path=str(resolved_socket_path),
    )
    owner_ids = _socket_owner_ids()
    if owner_ids is not None:
        os.chown(resolved_socket_path, owner_ids[0], owner_ids[1])
        os.chmod(resolved_socket_path, 0o660)
    else:
        os.chmod(resolved_socket_path, 0o600)
    try:
        async with server:
            try:
                await server.serve_forever()
            except asyncio.CancelledError:
                debug_os_sandbox_flow("helper.server_cancelled")
                return 0
    finally:
        await proxy.close()
        if resolved_socket_path.exists():
            resolved_socket_path.unlink()
    return 0
