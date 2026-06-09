from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from democrai.core.infrastructure.sandbox.os.factory import get_os_sandbox_provider
from democrai.core.infrastructure.sandbox.os.launch_policy import (
    NETWORK_ALLOW_ALL,
    NETWORK_DENY,
    NETWORK_PROXY,
    SandboxLaunchPolicy,
    build_launch_policy,
    policy_from_payload,
)
from democrai.core.runtime.foundation.app import app_ctx

_LAUNCH_READY_ENV = "DEMOCRAI_OS_SANDBOX_LAUNCH_READY_FILE"


def run_subprocess(
    command: list[str],
    *,
    cwd: str | None = None,
    check: bool = False,
    text: bool = True,
    capture_output: bool = True,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
    input: Any = None,
) -> subprocess.CompletedProcess[Any]:
    if not _os_sandbox_enabled():
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            check=bool(check),
            text=bool(text),
            capture_output=bool(capture_output),
            timeout=timeout,
            env=env,
            input=input,
        )

    launcher_env = _with_os_sandbox_helper_env(env)
    runtime_env = _without_os_sandbox_helper_env(launcher_env)
    local_broker = _ensure_spawn_broker_for_launch(runtime_env)
    ready_file = _new_launch_ready_file()
    launcher_env[_LAUNCH_READY_ENV] = str(ready_file)
    policy = _build_policy(command=command, cwd=cwd, env=runtime_env)
    policy, _appcontainer_sid, proxy_session_id = _prepare_policy_for_launch(policy, runtime_env)
    if _spawn_broker_available():
        from democrai.core.infrastructure.sandbox.spawn_broker import (
            popen_via_broker,
        )

        process = popen_via_broker(
            policy,
            command=command,
            stdin=subprocess.PIPE if input is not None else None,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=text,
        )
        try:
            stdout, stderr = process.communicate(input=input, timeout=timeout)
            completed = subprocess.CompletedProcess(
                command,
                process.returncode,
                stdout,
                stderr,
            )
            if check and completed.returncode:
                raise subprocess.CalledProcessError(
                    completed.returncode,
                    command,
                    output=stdout,
                    stderr=stderr,
                )
            return completed
        finally:
            process.cleanup()
            _close_local_spawn_broker(local_broker)
            _stop_launch_proxy_session(proxy_session_id)
    policy_path = _write_policy(policy)
    process: subprocess.Popen[Any] | None = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "democrai.core.infrastructure.sandbox.launcher", str(policy_path)],
            text=bool(text),
            stdin=subprocess.PIPE if input is not None else None,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            env=launcher_env,
        )
        _apply_launch_network_policy(policy, process.pid)
        _release_launch_ready_file(ready_file)
        stdout, stderr = process.communicate(input=input, timeout=timeout)
        completed = subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout,
            stderr,
        )
        if check and completed.returncode:
            raise subprocess.CalledProcessError(
                completed.returncode,
                command,
                output=stdout,
                stderr=stderr,
            )
        return completed
    except Exception:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate()
        raise
    finally:
        _release_launch_ready_file(ready_file)
        _cleanup_launch_ready_file(ready_file)
        _stop_launch_proxy_session(proxy_session_id)
        _close_local_spawn_broker(local_broker)
        try:
            policy_path.unlink()
        except OSError:
            pass


def popen(
    command: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    stdin: Any = None,
    stdout: Any = None,
    stderr: Any = None,
    text: bool | None = None,
    state: dict[str, Any] | None = None,
) -> subprocess.Popen[Any]:
    if not _os_sandbox_enabled():
        return subprocess.Popen(
            command,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            text=text,
        )

    launcher_env = _with_os_sandbox_helper_env(env)
    runtime_env = _without_os_sandbox_helper_env(launcher_env)
    local_broker = _ensure_spawn_broker_for_launch(runtime_env)
    ready_file = _new_launch_ready_file()
    launcher_env[_LAUNCH_READY_ENV] = str(ready_file)
    policy = _build_policy(command=command, cwd=cwd, env=runtime_env, state=state)
    policy, appcontainer_sid, proxy_session_id = _prepare_policy_for_launch(policy, runtime_env)
    if _spawn_broker_available():
        from democrai.core.infrastructure.sandbox.spawn_broker import (
            popen_via_broker,
        )

        process = popen_via_broker(
            policy,
            command=command,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            text=text,
        )
        if appcontainer_sid:
            setattr(process, "democrai_os_sandbox_appcontainer_sid", appcontainer_sid)
        if proxy_session_id:
            setattr(process, "democrai_os_sandbox_proxy_session_id", proxy_session_id)
        _attach_local_spawn_broker(process, local_broker)
        return process
    policy_path = _write_policy(policy)
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "democrai.core.infrastructure.sandbox.launcher", str(policy_path)],
            env=launcher_env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            text=text,
        )
        _apply_launch_network_policy(policy, process.pid)
        _release_launch_ready_file(ready_file)
        if appcontainer_sid:
            setattr(process, "democrai_os_sandbox_appcontainer_sid", appcontainer_sid)
        if proxy_session_id:
            setattr(process, "democrai_os_sandbox_proxy_session_id", proxy_session_id)
        return process
    except Exception:
        _release_launch_ready_file(ready_file)
        _cleanup_launch_ready_file(ready_file)
        _stop_launch_proxy_session(proxy_session_id)
        _close_local_spawn_broker(local_broker)
        try:
            policy_path.unlink()
        except OSError:
            pass
        raise


def _os_sandbox_enabled() -> bool:
    if sys.platform in {"darwin", "win32"} and _spawn_broker_available():
        return True
    config = getattr(app_ctx(), "config", None)
    getter = getattr(config, "get", None)
    if not callable(getter):
        return False
    return bool(getter("sandbox.os.enabled", False))


def _with_os_sandbox_helper_env(env: dict[str, str] | None) -> dict[str, str]:
    resolved = (
        {str(key): str(value) for key, value in dict(env).items()}
        if isinstance(env, dict)
        else dict(os.environ)
    )
    if not _os_sandbox_enabled():
        return resolved
    from democrai.core.infrastructure.sandbox.os.helper import (
        OS_SANDBOX_HELPER_SOCKET_ENV,
        OS_SANDBOX_HELPER_TOKEN_ENV,
        OS_SANDBOX_POLICY_FILE_ENV,
        _ensure_os_sandbox_helper_token,
        get_os_sandbox_helper_token,
        get_os_sandbox_helper_socket_path,
        get_os_sandbox_policy_file_path,
    )

    config = getattr(app_ctx(), "config", None)
    resolved.setdefault(
        OS_SANDBOX_HELPER_SOCKET_ENV,
        get_os_sandbox_helper_socket_path(config),
    )
    resolved.setdefault(
        OS_SANDBOX_POLICY_FILE_ENV,
        get_os_sandbox_policy_file_path(config),
    )
    token = get_os_sandbox_helper_token(config) or _ensure_os_sandbox_helper_token()
    if token:
        resolved.setdefault(OS_SANDBOX_HELPER_TOKEN_ENV, token)
    return resolved


def _without_os_sandbox_helper_env(env: dict[str, str]) -> dict[str, str]:
    from democrai.core.infrastructure.sandbox.os.helper import (
        OS_SANDBOX_HELPER_SOCKET_ENV,
        OS_SANDBOX_HELPER_TOKEN_ENV,
        OS_SANDBOX_POLICY_FILE_ENV,
    )

    resolved = dict(env)
    resolved.pop(OS_SANDBOX_HELPER_SOCKET_ENV, None)
    resolved.pop(OS_SANDBOX_HELPER_TOKEN_ENV, None)
    resolved.pop(OS_SANDBOX_POLICY_FILE_ENV, None)
    try:
        from democrai.core.infrastructure.sandbox.spawn_broker import (
            strip_broker_env,
        )

        resolved = strip_broker_env(resolved)
    except Exception:
        pass
    return resolved


def _spawn_broker_available() -> bool:
    if sys.platform not in {"darwin", "win32"}:
        return False
    try:
        from democrai.core.infrastructure.sandbox.spawn_broker import (
            broker_available,
        )

        return broker_available()
    except Exception:
        return False


def _ensure_spawn_broker_for_launch(env: dict[str, str]) -> Any:
    if sys.platform not in {"darwin", "win32"}:
        return None
    if _spawn_broker_available():
        return None
    if _current_process_is_os_sandboxed():
        raise RuntimeError("spawn_broker_required_in_sandboxed_process")
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    with process_guard_bypass_context():
        from democrai.core.infrastructure.sandbox.spawn_broker import (
            broker_env,
            start_spawn_broker,
        )

        broker = start_spawn_broker()
        values = broker_env(broker)
        os.environ.update(values)
    env.update(values)
    return broker


def _current_process_is_os_sandboxed() -> bool:
    if str(os.environ.get("DEMOCRAI_CORE_OS_SANDBOX_REEXEC") or "").strip() == "1":
        return True
    if str(os.environ.get("DEMOCRAI_CORE_PROCESS") or "").strip() == "1":
        return True
    return False


def _attach_local_spawn_broker(process: Any, broker: Any) -> None:
    if broker is not None:
        setattr(process, "democrai_local_spawn_broker", broker)
        cleanup = getattr(process, "cleanup", None)
        if callable(cleanup):
            def _cleanup_with_broker(*args, **kwargs):
                try:
                    return cleanup(*args, **kwargs)
                finally:
                    _close_local_spawn_broker(broker)

            setattr(process, "cleanup", _cleanup_with_broker)


def _close_local_spawn_broker(broker: Any) -> None:
    if broker is None:
        return
    try:
        from democrai.core.infrastructure.sandbox.spawn_broker import (
            SPAWN_BROKER_SOCKET_ENV,
            SPAWN_BROKER_TOKEN_ENV,
        )

        socket_path = str(getattr(broker, "socket_path", "") or "")
        if socket_path and str(os.environ.get(SPAWN_BROKER_SOCKET_ENV) or "") == socket_path:
            os.environ.pop(SPAWN_BROKER_SOCKET_ENV, None)
            os.environ.pop(SPAWN_BROKER_TOKEN_ENV, None)
    except Exception:
        pass
    try:
        broker.close()
    except Exception:
        pass
    try:
        from democrai.core.infrastructure.sandbox.spawn_broker import (
            broker_available,
        )

        return broker_available()
    except Exception:
        return False


def _popen_via_spawn_broker(
    policy: SandboxLaunchPolicy,
    *,
    command: list[str],
    stdin: Any = None,
    stdout: Any = None,
    stderr: Any = None,
    text: bool | None = None,
):
    from democrai.core.infrastructure.sandbox.spawn_broker import popen_via_broker

    return popen_via_broker(
        policy,
        command=command,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        text=text,
    )


def _build_policy(
    *,
    command: list[str],
    cwd: str | None,
    env: dict[str, str] | None,
    state: dict[str, Any] | None = None,
) -> SandboxLaunchPolicy:
    from democrai.core.infrastructure.sandbox import process_guard as process_guard_mod

    state = dict(process_guard_mod._state() if state is None else state)
    return build_launch_policy(
        command=command,
        cwd=cwd,
        env=env,
        state=state,
        allow_all_network=bool(state.get("os_sandbox_network_allow_all")),
    )


def _write_policy(policy: SandboxLaunchPolicy) -> Path:
    payload = policy.to_dict()
    fd, raw_path = tempfile.mkstemp(prefix="democrai_subprocess_", suffix=".json")
    path = Path(raw_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return path


def _attach_windows_shared_memory_sid(
    policy: SandboxLaunchPolicy,
    env: dict[str, str],
) -> str:
    if sys.platform != "win32":
        return ""
    from democrai.core.infrastructure.sandbox.os.windows.appcontainer import (
        shared_memory_package_sid,
    )

    package_sid = shared_memory_package_sid(policy)
    if package_sid:
        env["DEMOCRAI_OS_SANDBOX_APPCONTAINER_SID"] = package_sid
    return package_sid


def _prepare_policy_for_launch(
    policy: SandboxLaunchPolicy,
    env: dict[str, str],
) -> tuple[SandboxLaunchPolicy, str, str]:
    policy, proxy_session_id = _prepare_network_for_launch(policy, env)
    package_sid = _attach_windows_shared_memory_sid(policy, env)
    if package_sid:
        return replace(policy, env=dict(env)), package_sid, proxy_session_id
    return replace(policy, env=dict(env)), "", proxy_session_id


def _new_launch_ready_file() -> Path:
    fd, raw_path = tempfile.mkstemp(prefix="democrai_sandbox_launch_ready_", suffix=".flag")
    os.close(fd)
    path = Path(raw_path)
    path.unlink()
    return path


def _release_launch_ready_file(path: Path) -> None:
    try:
        path.write_text("ready\n", encoding="ascii")
    except OSError:
        pass


def _cleanup_launch_ready_file(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _prepare_network_for_launch(
    policy: SandboxLaunchPolicy,
    env: dict[str, str],
) -> tuple[SandboxLaunchPolicy, str]:
    if policy.network_mode != NETWORK_PROXY:
        return policy, ""
    if _spawn_broker_available():
        return replace(policy, env=dict(env)), ""
    from democrai.core.infrastructure.sandbox.os.helper import (
        start_application_network_proxy_session_with_helper,
    )
    from democrai.core.infrastructure.sandbox.os.models import (
        ApplicationNetworkAllowlist,
    )
    from democrai.core.infrastructure.sandbox.os.base import (
        _network_endpoint_from_target,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    endpoints = [
        endpoint
        for endpoint in (_network_endpoint_from_target(item) for item in policy.network_endpoints)
        if endpoint is not None
    ]
    if not endpoints:
        raise RuntimeError("os_sandbox_proxy_endpoints_required")
    config = getattr(app_ctx(), "config", None)
    with process_guard_bypass_context():
        session = start_application_network_proxy_session_with_helper(
            ApplicationNetworkAllowlist(endpoints=endpoints),
            config=config,
        )
    proxy_url = str(session.get("proxy_url") or "").strip()
    if not proxy_url:
        raise RuntimeError("os_sandbox_proxy_url_missing")
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
        env[key] = proxy_url
    env["NO_PROXY"] = "127.0.0.1,localhost,::1"
    env["no_proxy"] = "127.0.0.1,localhost,::1"
    return replace(policy, env=dict(env)), str(session.get("session_id") or "").strip()


def _apply_launch_network_policy(policy: SandboxLaunchPolicy, pid: int) -> None:
    if policy.network_mode == NETWORK_ALLOW_ALL:
        return
    from democrai.core.infrastructure.sandbox.os.base import proxy_endpoint_payload
    from democrai.core.infrastructure.sandbox.os.helper import (
        apply_application_network_allowlist_with_helper,
    )
    from democrai.core.infrastructure.sandbox.os.models import (
        ApplicationNetworkAllowlist,
        NetworkEndpoint,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    endpoints = []
    if policy.network_mode == NETWORK_PROXY:
        proxy_url = ""
        if policy.env is not None:
            proxy_url = str(policy.env.get("ALL_PROXY") or policy.env.get("all_proxy") or "")
        proxy_endpoint = proxy_endpoint_payload(proxy_url)
        endpoints.append(
            NetworkEndpoint(
                host=str(proxy_endpoint["host"]),
                port=int(proxy_endpoint["port"]),
                protocol=str(proxy_endpoint["protocol"]),
                source=str(proxy_endpoint["source"]),
                purpose=str(proxy_endpoint["purpose"]),
            )
        )
    elif policy.network_mode != NETWORK_DENY:
        raise RuntimeError(f"os_sandbox_invalid_network_mode:{policy.network_mode}")
    from democrai.core.infrastructure.sandbox.os.factory import get_helper_backend

    if not getattr(get_helper_backend(), "supports_pid_enforcement", False):
        return
    config = getattr(app_ctx(), "config", None)
    with process_guard_bypass_context():
        apply_application_network_allowlist_with_helper(
            ApplicationNetworkAllowlist(endpoints=endpoints),
            pid=int(pid),
            config=config,
        )


def _stop_launch_proxy_session(session_id: str) -> None:
    if not session_id:
        return
    from democrai.core.infrastructure.sandbox.os.helper import (
        stop_application_network_proxy_session_with_helper,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    try:
        with process_guard_bypass_context():
            stop_application_network_proxy_session_with_helper(
                session_id,
                config=getattr(app_ctx(), "config", None),
            )
    except Exception:
        pass


def _run_child(policy_path: str) -> None:
    with open(policy_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    try:
        Path(policy_path).unlink()
    except OSError:
        pass

    policy = policy_from_payload(payload)
    _wait_for_launch_ready()
    get_os_sandbox_provider().run(policy)


def _wait_for_launch_ready() -> None:
    raw_path = str(os.environ.get(_LAUNCH_READY_ENV) or "").strip()
    if not raw_path:
        return
    path = Path(raw_path)
    for _ in range(1000):
        if path.exists():
            _cleanup_launch_ready_file(path)
            return
        time.sleep(0.01)
    raise RuntimeError(f"os_sandbox_launch_ready_timeout:{path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("sandbox_launcher_policy_required")
    _run_child(sys.argv[1])
