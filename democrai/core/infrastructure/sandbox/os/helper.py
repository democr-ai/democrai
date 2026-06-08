from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import shutil
import uuid
from pathlib import Path
from typing import Any

from democrai.core.platform.utils.debug import debug_os_sandbox_flow
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import (
    data_dir,
    get_base_dir,
    is_frozen,
    logs_dir,
    runtime_ipc_dir,
    runtime_unix_socket_path,
    state_dir,
)
from democrai.core.runtime.lifecycle.process_supervisor import process_supervisor

from .linux import ensure_linux_network_enforcement_ready
from .models import ApplicationNetworkAllowlist


OS_SANDBOX_HELPER_SOCKET_ENV = "DEMOCRAI_OS_SANDBOX_HELPER_SOCKET"
OS_SANDBOX_POLICY_FILE_ENV = "DEMOCRAI_OS_SANDBOX_POLICY_FILE"
OS_SANDBOX_HELPER_TOKEN_ENV = "DEMOCRAI_OS_SANDBOX_HELPER_TOKEN"
_POLICY_WRITE_ALLOWED: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "os_sandbox_policy_write_allowed",
    default=False,
)
_POLICY_APPLY_LOCK = threading.RLock()


@contextlib.contextmanager
def _allow_os_sandbox_policy_write():
    token = _POLICY_WRITE_ALLOWED.set(True)
    try:
        yield
    finally:
        _POLICY_WRITE_ALLOWED.reset(token)


def _process_scoped_config_path(value: str) -> str:
    pid = str(os.getpid())
    configured = value.strip()
    if "{pid}" in configured:
        return configured.replace("{pid}", pid)
    path = Path(configured).expanduser()
    return str(path.with_name(f"{path.stem}_{pid}{path.suffix}"))


def get_os_sandbox_helper_socket_path(config: Any | None = None) -> str:
    inherited = str(os.environ.get(OS_SANDBOX_HELPER_SOCKET_ENV) or "").strip()
    if inherited:
        return inherited
    resolved_config = app_ctx().config if config is None else config
    getter = getattr(resolved_config, "get", None)
    if callable(getter):
        configured = str(getter("sandbox.os.helper_socket", "") or "").strip()
        if configured:
            return _process_scoped_config_path(configured)
    return str(runtime_unix_socket_path(f"os_sandbox_helper_{os.getpid()}.sock").resolve())


def get_os_sandbox_policy_file_path(config: Any | None = None) -> str:
    inherited = str(os.environ.get(OS_SANDBOX_POLICY_FILE_ENV) or "").strip()
    if inherited:
        return inherited
    resolved_config = app_ctx().config if config is None else config
    getter = getattr(resolved_config, "get", None)
    if callable(getter):
        configured = str(getter("sandbox.os.policy_file", "") or "").strip()
        if configured:
            return _process_scoped_config_path(configured)
    return str((data_dir() / f"os_sandbox_allowlist_{os.getpid()}.json").resolve())


def get_os_sandbox_helper_token(config: Any | None = None) -> str:
    inherited = str(os.environ.get(OS_SANDBOX_HELPER_TOKEN_ENV) or "").strip()
    if inherited:
        return inherited
    return str(getattr(app_ctx(), "os_sandbox_helper_token", "") or "").strip()


def _ensure_os_sandbox_helper_token() -> str:
    token = get_os_sandbox_helper_token()
    if token:
        return token
    token = secrets.token_urlsafe(32)
    setattr(app_ctx(), "os_sandbox_helper_token", token)
    return token


def _require_os_sandbox_helper_token(config: Any | None = None) -> str:
    token = get_os_sandbox_helper_token(config)
    if not token:
        raise RuntimeError("os_sandbox_helper_token_missing")
    return token


def get_os_sandbox_refresh_seconds(config: Any | None = None) -> int:
    resolved_config = app_ctx().config if config is None else config
    getter = getattr(resolved_config, "get", None)
    if callable(getter):
        try:
            return max(0, int(getter("sandbox.os.refresh_seconds", 60) or 60))
        except Exception:
            return 60
    return 60


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _cleanup_stale_helper_sockets() -> None:
    roots = [state_dir(), runtime_ipc_dir()]
    seen: set[Path] = set()
    for root in roots:
        for path in root.glob("os_sandbox_helper_*.sock"):
            if path in seen:
                continue
            seen.add(path)
            _cleanup_stale_helper_socket(path)


def _cleanup_stale_helper_socket(path: Path) -> None:
    stem = path.stem
    raw_pid = stem.removeprefix("os_sandbox_helper_")
    if not raw_pid.isdigit() or _pid_is_alive(int(raw_pid)):
        return
    try:
        path.unlink()
        debug_os_sandbox_flow("helper.stale_socket_removed", socket_path=str(path))
    except Exception as exc:
        debug_os_sandbox_flow(
            "helper.stale_socket_remove_failed",
            socket_path=str(path),
            error=str(exc),
        )


def _cleanup_stale_policy_files() -> None:
    for path in data_dir().glob("os_sandbox_allowlist_*.json"):
        stem = path.stem
        raw_pid = stem.removeprefix("os_sandbox_allowlist_")
        if not raw_pid.isdigit() or _pid_is_alive(int(raw_pid)):
            continue
        try:
            path.unlink()
            debug_os_sandbox_flow("helper.stale_policy_removed", policy_file=str(path))
        except Exception as exc:
            debug_os_sandbox_flow(
                "helper.stale_policy_remove_failed",
                policy_file=str(path),
                error=str(exc),
            )


def _allowlist_to_payload(allowlist: ApplicationNetworkAllowlist) -> dict[str, Any]:
    return {
        "endpoints": [
            {
                "host": endpoint.host,
                "port": endpoint.port,
                "protocol": endpoint.protocol,
                "source": endpoint.source,
                "purpose": endpoint.purpose,
            }
            for endpoint in list(allowlist.endpoints or [])
        ]
    }


def _debug_helper_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    if "proxy_url" in sanitized:
        sanitized["proxy_url"] = "<redacted>"
    if "token" in sanitized:
        sanitized["token"] = "<redacted>"
    return sanitized


def _debug_helper_command(command: list[str]) -> list[str]:
    sanitized = list(command)
    for index, item in enumerate(sanitized[:-1]):
        if item == "--os-sandbox-helper-token":
            sanitized[index + 1] = "<redacted>"
    return sanitized


async def _request_helper(
    *,
    socket_path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    request_payload = {"token": _require_os_sandbox_helper_token(), **dict(payload)}
    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        debug_os_sandbox_flow(
            "helper.client_request",
            socket_path=socket_path,
            payload=_debug_helper_payload(request_payload),
        )
        writer.write((json.dumps(request_payload) + "\n").encode("utf-8"))
        await writer.drain()
        raw = await reader.readline()
    finally:
        writer.close()
        await writer.wait_closed()
    if not raw:
        raise RuntimeError("os_sandbox_helper_empty_response")
    response = json.loads(raw.decode("utf-8"))
    if not isinstance(response, dict):
        raise RuntimeError("os_sandbox_helper_invalid_response")
    debug_os_sandbox_flow(
        "helper.client_response",
        socket_path=socket_path,
        response=_debug_helper_payload(response),
    )
    if not bool(response.get("ok")):
        raise RuntimeError(str(response.get("error") or "os_sandbox_helper_request_failed"))
    return response


async def _request_helper_ready_async(config: Any | None = None) -> None:
    socket_path = get_os_sandbox_helper_socket_path(config)
    _cleanup_stale_helper_sockets()
    _cleanup_stale_policy_files()
    if not str(os.environ.get(OS_SANDBOX_HELPER_SOCKET_ENV) or "").strip():
        _ensure_os_sandbox_helper_token()
    try:
        await _request_helper(socket_path=socket_path, payload={"action": "ping"})
        return
    except FileNotFoundError as exc:
        if not str(os.environ.get(OS_SANDBOX_HELPER_SOCKET_ENV) or "").strip():
            strategy = _helper_autostart_strategy()
            if strategy is not None:
                _restart_os_sandbox_helper_process(socket_path)
                await _wait_for_helper_async(
                    socket_path,
                    timeout_seconds=60.0 if strategy in {"pkexec", "sudo"} else 3.0,
                )
                return
            start_command = " ".join(_sudo_helper_command(socket_path, config))
            raise RuntimeError(
                "os_sandbox_helper_not_running:"
                f"{socket_path}:start_with={start_command}"
            ) from exc
        raise RuntimeError(
            f"os_sandbox_helper_not_running:{socket_path}"
        ) from exc
    except ConnectionRefusedError as exc:
        if not str(os.environ.get(OS_SANDBOX_HELPER_SOCKET_ENV) or "").strip():
            strategy = _helper_autostart_strategy()
            if strategy is not None:
                _restart_os_sandbox_helper_process(socket_path)
                await _wait_for_helper_async(
                    socket_path,
                    timeout_seconds=60.0 if strategy in {"pkexec", "sudo"} else 3.0,
                )
                return
        raise RuntimeError(
            f"os_sandbox_helper_unreachable:{socket_path}"
        ) from exc


def _run_async_in_thread(
    coro_factory,
) -> Any:
    result: Any = None
    error: BaseException | None = None

    def runner() -> None:
        nonlocal result, error
        try:
            result = asyncio.run(coro_factory())
        except BaseException as exc:  # pragma: no cover
            error = exc

    thread = threading.Thread(target=runner, name="os-sandbox-helper-request", daemon=True)
    thread.start()
    thread.join()
    if error is not None:
        raise error
    return result


def _run_helper_request_sync(
    *,
    socket_path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_request_helper(socket_path=socket_path, payload=payload))
    result = _run_async_in_thread(
        lambda: _request_helper(socket_path=socket_path, payload=payload)
    )
    if result is None:
        raise RuntimeError("os_sandbox_helper_request_failed_without_response")
    return result


def _helper_module_command_prefix() -> list[str]:
    if is_frozen():
        return [os.path.abspath(sys.executable), "--os-sandbox-helper-process"]
    installed_script = _installed_helper_script()
    if installed_script:
        return [installed_script]
    return [
        sys.executable,
        str(Path(__file__).resolve().with_name("helper_entrypoint.py")),
    ]


def _installed_helper_script() -> str:
    script_name = "democrai-os-sandbox-helper"
    candidates = [
        Path(sys.executable).resolve().parent / script_name,
        Path(sys.executable).resolve().parent / f"{script_name}.exe",
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    resolved = shutil.which(script_name)
    return str(resolved or "")


def _application_root() -> str:
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return str(Path(get_base_dir()).resolve().parent)


def _helper_autostart_env() -> dict[str, str]:
    env = dict(os.environ)
    app_root = _application_root()
    existing = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = (
        f"{app_root}{os.pathsep}{existing}" if existing else app_root
    )
    return env


def _helper_autostart_log_file():
    path = _helper_autostart_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("ab")


def _helper_autostart_log_path() -> Path:
    return logs_dir() / "os_sandbox_helper_autostart.log"


def _helper_autostart_log_tail() -> str:
    try:
        path = _helper_autostart_log_path()
        if not path.exists():
            return ""
        data = path.read_bytes()[-8000:]
        return data.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _helper_command(socket_path: str, config: Any | None = None) -> list[str]:
    return [
        *_helper_module_command_prefix(),
        "--os-sandbox-helper-socket",
        socket_path,
        "--os-sandbox-helper-policy-file",
        get_os_sandbox_policy_file_path(config),
        "--os-sandbox-helper-refresh-seconds",
        str(get_os_sandbox_refresh_seconds()),
        "--os-sandbox-helper-parent-pid",
        str(os.getpid()),
        "--os-sandbox-helper-token",
        _ensure_os_sandbox_helper_token(),
    ]


def _pkexec_helper_command(socket_path: str, config: Any | None = None) -> list[str]:
    return [
        "pkexec",
        *_helper_module_command_prefix(),
        "--os-sandbox-helper-socket",
        socket_path,
        "--os-sandbox-helper-policy-file",
        get_os_sandbox_policy_file_path(config),
        "--os-sandbox-helper-refresh-seconds",
        str(get_os_sandbox_refresh_seconds()),
        "--os-sandbox-helper-parent-pid",
        str(os.getpid()),
        "--os-sandbox-helper-token",
        _ensure_os_sandbox_helper_token(),
    ]


def _sudo_helper_command(socket_path: str, config: Any | None = None) -> list[str]:
    return [
        "sudo",
        *_helper_module_command_prefix(),
        "--os-sandbox-helper-socket",
        socket_path,
        "--os-sandbox-helper-policy-file",
        get_os_sandbox_policy_file_path(config),
        "--os-sandbox-helper-refresh-seconds",
        str(get_os_sandbox_refresh_seconds()),
        "--os-sandbox-helper-parent-pid",
        str(os.getpid()),
        "--os-sandbox-helper-token",
        _ensure_os_sandbox_helper_token(),
    ]


def _can_autostart_helper() -> bool:
    try:
        ensure_linux_network_enforcement_ready()
    except Exception as exc:
        debug_os_sandbox_flow("helper.autostart_unavailable", error=str(exc))
        return False
    return True


def _can_pkexec_autostart_helper() -> bool:
    return shutil.which("pkexec") is not None


def _can_sudo_autostart_helper() -> bool:
    return shutil.which("sudo") is not None


def _helper_autostart_strategy() -> str | None:
    if _can_autostart_helper():
        return "direct"
    runtime_mode = str(getattr(app_ctx(), "runtime_mode", "") or "").strip().lower()
    if runtime_mode == "desktop" and _can_pkexec_autostart_helper():
        return "pkexec"
    if runtime_mode != "desktop" and _can_sudo_autostart_helper():
        return "sudo"
    return None


def _cleanup_helper_socket(socket_path: str) -> None:
    try:
        path = Path(str(socket_path or "").strip()).expanduser().resolve()
    except Exception:
        return
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def cleanup_os_sandbox_policy_file(config: Any | None = None) -> None:
    try:
        path = Path(get_os_sandbox_policy_file_path(config)).expanduser().resolve()
    except Exception:
        return
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def _stop_tracked_helper_process() -> None:
    existing = getattr(app_ctx(), "os_sandbox_helper_process", None)
    if existing is None:
        return
    try:
        process_supervisor.terminate(existing)
    except Exception:
        try:
            existing.kill()
        except Exception:
            pass
    finally:
        process_supervisor.unregister(existing)
        app_ctx().os_sandbox_helper_process = None
        with contextlib.suppress(Exception):
            setattr(app_ctx(), "os_sandbox_helper_token", "")


def _start_os_sandbox_helper_process(socket_path: str) -> subprocess.Popen[bytes]:
    existing = getattr(app_ctx(), "os_sandbox_helper_process", None)
    if existing is not None and existing.poll() is None:
        return existing
    strategy = _helper_autostart_strategy()
    if strategy is None:
        raise RuntimeError("os_sandbox_helper_autostart_unavailable")
    if strategy == "direct":
        command = _helper_command(socket_path)
    elif strategy == "pkexec":
        command = _pkexec_helper_command(socket_path)
    else:
        command = _sudo_helper_command(socket_path)
    debug_os_sandbox_flow(
        "helper.autostart_spawn",
        cmd=_debug_helper_command(command),
        socket_path=socket_path,
        strategy=strategy,
    )
    popen_kwargs: dict[str, Any] = {
        "close_fds": True,
        "stdin": subprocess.DEVNULL,
        "stdout": _helper_autostart_log_file(),
        "stderr": subprocess.STDOUT,
        "cwd": _application_root(),
        "env": _helper_autostart_env(),
    }
    if strategy == "direct":
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(command, **popen_kwargs)
    app_ctx().os_sandbox_helper_process = proc
    process_supervisor.register(proc, name="os-sandbox-helper")
    return proc


def _restart_os_sandbox_helper_process(socket_path: str) -> subprocess.Popen[bytes]:
    debug_os_sandbox_flow("helper.autostart_restart", socket_path=socket_path)
    _stop_tracked_helper_process()
    _cleanup_helper_socket(socket_path)
    return _start_os_sandbox_helper_process(socket_path)


async def _wait_for_helper_async(socket_path: str, *, timeout_seconds: float = 3.0) -> None:
    deadline = time.time() + float(timeout_seconds)
    last_error: Exception | None = None
    while time.time() < deadline:
        proc = getattr(app_ctx(), "os_sandbox_helper_process", None)
        if proc is not None:
            try:
                returncode = proc.poll()
            except Exception:
                returncode = None
            if returncode is not None:
                log_tail = _helper_autostart_log_tail()
                raise RuntimeError(
                    f"os_sandbox_helper_process_exited:{int(returncode)}:{socket_path}"
                    + (f":log_tail={log_tail}" if log_tail else "")
                )
        try:
            await _request_helper(socket_path=socket_path, payload={"action": "ping"})
            return
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.1)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"os_sandbox_helper_wait_timeout:{socket_path}")


def ensure_os_sandbox_helper_ready(config: Any | None = None) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_request_helper_ready_async(config))
    _run_async_in_thread(lambda: _request_helper_ready_async(config))
    return None


async def ensure_os_sandbox_helper_ready_async(config: Any | None = None) -> None:
    await _request_helper_ready_async(config)


def apply_application_network_allowlist_with_helper(
    allowlist: ApplicationNetworkAllowlist,
    *,
    pid: int | None = None,
    config: Any | None = None,
) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            apply_application_network_allowlist_with_helper_async(
                allowlist,
                pid=pid,
                config=config,
            )
        )
    _run_async_in_thread(
        lambda: apply_application_network_allowlist_with_helper_async(
            allowlist,
            pid=pid,
            config=config,
        )
    )


def apply_current_application_network_allowlist_with_helper(
    *,
    pid: int | None = None,
    config: Any | None = None,
) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            apply_current_application_network_allowlist_with_helper_async(
                pid=pid,
                config=config,
            )
        )
    _run_async_in_thread(
        lambda: apply_current_application_network_allowlist_with_helper_async(
            pid=pid,
            config=config,
        )
    )


async def apply_current_application_network_allowlist_with_helper_async(
    *,
    pid: int | None = None,
    config: Any | None = None,
) -> None:
    socket_path = get_os_sandbox_helper_socket_path(config)
    _require_os_sandbox_helper_token(config)
    await ensure_os_sandbox_helper_ready_async(config)
    await _request_helper(
        socket_path=socket_path,
        payload={"action": "apply", "pid": int(pid or os.getpid())},
    )


async def apply_application_network_allowlist_with_helper_async(
    allowlist: ApplicationNetworkAllowlist,
    *,
    pid: int | None = None,
    config: Any | None = None,
) -> None:
    _require_os_sandbox_helper_token(config)
    with _POLICY_APPLY_LOCK:
        with _allow_os_sandbox_policy_write():
            write_os_sandbox_policy_file(allowlist, config=config)
        await apply_current_application_network_allowlist_with_helper_async(
            pid=pid,
            config=config,
        )


async def start_application_network_proxy_session_with_helper_async(
    allowlist: ApplicationNetworkAllowlist,
    *,
    config: Any | None = None,
) -> dict[str, str]:
    socket_path = get_os_sandbox_helper_socket_path(config)
    _require_os_sandbox_helper_token(config)
    await ensure_os_sandbox_helper_ready_async(config)
    response = await _request_helper(
        socket_path=socket_path,
        payload={
            "action": "start_proxy_session",
            **_allowlist_to_payload(allowlist),
        },
    )
    session_id = str(response.get("session_id") or "").strip()
    proxy_url = str(response.get("proxy_url") or "").strip()
    if not session_id or not proxy_url:
        raise RuntimeError("os_sandbox_helper_invalid_proxy_session_response")
    return {"session_id": session_id, "proxy_url": proxy_url}


def start_application_network_proxy_session_with_helper(
    allowlist: ApplicationNetworkAllowlist,
    *,
    config: Any | None = None,
) -> dict[str, str]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            start_application_network_proxy_session_with_helper_async(
                allowlist,
                config=config,
            )
        )
    result = _run_async_in_thread(
        lambda: start_application_network_proxy_session_with_helper_async(
            allowlist,
            config=config,
        )
    )
    if not isinstance(result, dict):
        raise RuntimeError("os_sandbox_helper_invalid_proxy_session_response")
    return {"session_id": str(result["session_id"]), "proxy_url": str(result["proxy_url"])}


async def update_application_network_proxy_session_with_helper_async(
    session_id: str,
    allowlist: ApplicationNetworkAllowlist,
    *,
    config: Any | None = None,
) -> dict[str, str]:
    resolved = str(session_id or "").strip()
    if not resolved:
        raise RuntimeError("os_sandbox_proxy_session_id_required")
    socket_path = get_os_sandbox_helper_socket_path(config)
    _require_os_sandbox_helper_token(config)
    await ensure_os_sandbox_helper_ready_async(config)
    response = await _request_helper(
        socket_path=socket_path,
        payload={
            "action": "update_proxy_session",
            "session_id": resolved,
            **_allowlist_to_payload(allowlist),
        },
    )
    response_session_id = str(response.get("session_id") or "").strip()
    proxy_url = str(response.get("proxy_url") or "").strip()
    if response_session_id != resolved or not proxy_url:
        raise RuntimeError("os_sandbox_helper_invalid_proxy_session_response")
    return {"session_id": response_session_id, "proxy_url": proxy_url}


def update_application_network_proxy_session_with_helper(
    session_id: str,
    allowlist: ApplicationNetworkAllowlist,
    *,
    config: Any | None = None,
) -> dict[str, str]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            update_application_network_proxy_session_with_helper_async(
                session_id,
                allowlist,
                config=config,
            )
        )
    result = _run_async_in_thread(
        lambda: update_application_network_proxy_session_with_helper_async(
            session_id,
            allowlist,
            config=config,
        )
    )
    if not isinstance(result, dict):
        raise RuntimeError("os_sandbox_helper_invalid_proxy_session_response")
    return {"session_id": str(result["session_id"]), "proxy_url": str(result["proxy_url"])}


async def stop_application_network_proxy_session_with_helper_async(
    session_id: str,
    *,
    config: Any | None = None,
) -> None:
    resolved = str(session_id or "").strip()
    if not resolved:
        return
    socket_path = get_os_sandbox_helper_socket_path(config)
    _require_os_sandbox_helper_token(config)
    await ensure_os_sandbox_helper_ready_async(config)
    await _request_helper(
        socket_path=socket_path,
        payload={"action": "stop_proxy_session", "session_id": resolved},
    )


def stop_application_network_proxy_session_with_helper(
    session_id: str,
    *,
    config: Any | None = None,
) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            stop_application_network_proxy_session_with_helper_async(
                session_id,
                config=config,
            )
        )
    _run_async_in_thread(
        lambda: stop_application_network_proxy_session_with_helper_async(
            session_id,
            config=config,
        )
    )


def clear_application_network_allowlist_with_helper(
    *,
    pid: int | None = None,
    config: Any | None = None,
) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            clear_application_network_allowlist_with_helper_async(
                pid=pid,
                config=config,
            )
        )
    _run_async_in_thread(
        lambda: clear_application_network_allowlist_with_helper_async(
            pid=pid,
            config=config,
        )
    )


async def clear_application_network_allowlist_with_helper_async(
    *,
    pid: int | None = None,
    config: Any | None = None,
) -> None:
    socket_path = get_os_sandbox_helper_socket_path(config)
    _require_os_sandbox_helper_token(config)
    await ensure_os_sandbox_helper_ready_async(config)
    await _request_helper(
        socket_path=socket_path,
        payload={"action": "clear", "pid": int(pid or os.getpid())},
    )


def write_os_sandbox_policy_file(
    allowlist: ApplicationNetworkAllowlist,
    *,
    config: Any | None = None,
) -> str:
    if not _POLICY_WRITE_ALLOWED.get():
        raise RuntimeError("os_sandbox_policy_write_denied")
    policy_path = Path(get_os_sandbox_policy_file_path(config)).expanduser().resolve()
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        **_allowlist_to_payload(allowlist),
    }
    temp_path = policy_path.with_name(
        f"{policy_path.name}.tmp.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}"
    )
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, policy_path)
        os.chmod(policy_path, 0o600)
        try:
            dir_fd = os.open(str(policy_path.parent), os.O_RDONLY)
        except Exception:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass
    debug_os_sandbox_flow(
        "helper.policy_file_written",
        policy_file=str(policy_path),
        endpoint_count=len(allowlist.endpoints),
    )
    return str(policy_path)
