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

from democrai.core.infrastructure.sandbox.os.factory import (
    get_core_launch_strategy,
    get_os_sandbox_provider,
)
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
    policy, _appcontainer_sid, proxy_session_id = _prepare_policy_for_launch(
        policy, runtime_env
    )
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
            [
                sys.executable,
                "-m",
                "democrai.core.infrastructure.sandbox.launcher",
                str(policy_path),
            ],
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
    inherit_helper_env = _state_inherits_os_sandbox_helper_env(state)
    runtime_env = (
        launcher_env
        if inherit_helper_env
        else _without_os_sandbox_helper_env(launcher_env)
    )
    local_broker = _ensure_spawn_broker_for_launch(runtime_env)
    ready_file = _new_launch_ready_file()
    launcher_env[_LAUNCH_READY_ENV] = str(ready_file)
    policy = _build_policy(command=command, cwd=cwd, env=runtime_env, state=state)
    policy, appcontainer_sid, proxy_session_id = _prepare_policy_for_launch(
        policy, runtime_env
    )
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
            [
                sys.executable,
                "-m",
                "democrai.core.infrastructure.sandbox.launcher",
                str(policy_path),
            ],
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
    if get_core_launch_strategy().uses_spawn_broker and _spawn_broker_available():
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
        ensure_os_sandbox_helper_token,
        get_os_sandbox_helper_token,
        get_os_sandbox_helper_socket_path,
        get_os_sandbox_policy_file_path,
    )

    config = getattr(app_ctx(), "config", None)
    socket_path = (
        resolved.get(OS_SANDBOX_HELPER_SOCKET_ENV)
        or os.environ.get(OS_SANDBOX_HELPER_SOCKET_ENV)
        or get_os_sandbox_helper_socket_path(config)
    )
    policy_file = (
        resolved.get(OS_SANDBOX_POLICY_FILE_ENV)
        or os.environ.get(OS_SANDBOX_POLICY_FILE_ENV)
        or get_os_sandbox_policy_file_path(config)
    )
    token = (
        resolved.get(OS_SANDBOX_HELPER_TOKEN_ENV)
        or os.environ.get(OS_SANDBOX_HELPER_TOKEN_ENV)
        or get_os_sandbox_helper_token(config)
        or ensure_os_sandbox_helper_token()
    )
    resolved[OS_SANDBOX_HELPER_SOCKET_ENV] = socket_path
    resolved[OS_SANDBOX_POLICY_FILE_ENV] = policy_file
    if token:
        resolved[OS_SANDBOX_HELPER_TOKEN_ENV] = token
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


def _state_inherits_os_sandbox_helper_env(state: dict[str, Any] | None) -> bool:
    if not isinstance(state, dict):
        return False
    return bool(state.get("inherit_os_sandbox_helper_env", False))


def _spawn_broker_available() -> bool:
    if not get_core_launch_strategy().uses_spawn_broker:
        return False
    try:
        from democrai.core.infrastructure.sandbox.spawn_broker import (
            broker_available,
        )

        return broker_available()
    except Exception:
        return False


def _ensure_spawn_broker_for_launch(env: dict[str, str]) -> Any:
    if not get_core_launch_strategy().uses_spawn_broker:
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
        if (
            socket_path
            and str(os.environ.get(SPAWN_BROKER_SOCKET_ENV) or "") == socket_path
        ):
            os.environ.pop(SPAWN_BROKER_SOCKET_ENV, None)
            os.environ.pop(SPAWN_BROKER_TOKEN_ENV, None)
    except Exception:
        pass
    try:
        broker.close()
    except Exception:
        pass


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


def _prepare_policy_for_launch(
    policy: SandboxLaunchPolicy,
    env: dict[str, str],
) -> tuple[SandboxLaunchPolicy, str, str]:
    policy, proxy_session_id = _prepare_network_for_launch(policy, env)
    package_sid = get_os_sandbox_provider().prepare_launch_env(policy, env)
    return replace(policy, env=dict(env)), package_sid, proxy_session_id


def _new_launch_ready_file() -> Path:
    fd, raw_path = tempfile.mkstemp(
        prefix="democrai_sandbox_launch_ready_", suffix=".flag"
    )
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
    from democrai.core.infrastructure.sandbox.os.base import (
        _network_endpoint_from_target,
    )
    from democrai.core.infrastructure.sandbox.os.models import (
        ApplicationNetworkAllowlist,
    )
    from democrai.core.infrastructure.sandbox.os.proxy_session import (
        ProxySessionManager,
    )

    endpoints = [
        endpoint
        for endpoint in (
            _network_endpoint_from_target(item) for item in policy.network_endpoints
        )
        if endpoint is not None
    ]
    if not endpoints:
        raise RuntimeError("os_sandbox_proxy_endpoints_required")
    session_id = ProxySessionManager(
        getattr(app_ctx(), "config", None)
    ).start_for_env(ApplicationNetworkAllowlist(endpoints=endpoints), env)
    return replace(policy, env=dict(env)), session_id


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
            proxy_url = str(
                policy.env.get("ALL_PROXY") or policy.env.get("all_proxy") or ""
            )
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

    backend = get_helper_backend()
    if not getattr(backend, "supports_pid_enforcement", False):
        return
    # Some backends (Windows WFP) enforce inside their own spawn path, keyed on
    # the real sandboxed-child pid. Here ``process.pid`` is the intermediate
    # ``-m launcher`` wrapper (it runs from the normal interpreter and, on
    # Windows, CreateProcessAsUserW spawns a *separate* low-integrity child
    # rather than exec-replacing), so applying enforcement here would target the
    # wrong process. Those backends apply at spawn instead.
    if getattr(backend, "applies_enforcement_at_spawn", False):
        return
    config = getattr(app_ctx(), "config", None)
    with process_guard_bypass_context():
        apply_application_network_allowlist_with_helper(
            ApplicationNetworkAllowlist(endpoints=endpoints),
            pid=int(pid),
            config=config,
        )


def _stop_launch_proxy_session(session_id: str) -> None:
    from democrai.core.infrastructure.sandbox.os.proxy_session import (
        ProxySessionManager,
    )

    ProxySessionManager(getattr(app_ctx(), "config", None)).stop(session_id)


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
