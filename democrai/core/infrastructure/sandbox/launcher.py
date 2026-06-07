from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from democrai.core.infrastructure.sandbox.os.factory import get_os_sandbox_provider
from democrai.core.infrastructure.sandbox.os.launch_policy import (
    SandboxLaunchPolicy,
    build_launch_policy,
    policy_from_payload,
)
from democrai.core.runtime.foundation.app import app_ctx


def run_subprocess(
    command: list[str],
    *,
    cwd: str | None = None,
    check: bool = False,
    text: bool = True,
    capture_output: bool = True,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
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
        )

    child_env = _with_os_sandbox_helper_env(env)
    policy = _build_policy(command=command, cwd=cwd, env=child_env)
    policy, _appcontainer_sid = _prepare_policy_for_launch(policy, child_env)
    policy_path = _write_policy(policy)
    try:
        return subprocess.run(
            [sys.executable, "-m", "democrai.core.infrastructure.sandbox.launcher", str(policy_path)],
            check=bool(check),
            text=bool(text),
            capture_output=bool(capture_output),
            timeout=timeout,
            env=child_env,
        )
    finally:
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

    child_env = _with_os_sandbox_helper_env(env)
    policy = _build_policy(command=command, cwd=cwd, env=child_env, state=state)
    policy, appcontainer_sid = _prepare_policy_for_launch(policy, child_env)
    policy_path = _write_policy(policy)
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "democrai.core.infrastructure.sandbox.launcher", str(policy_path)],
            env=child_env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            text=text,
        )
        if appcontainer_sid:
            setattr(process, "democrai_os_sandbox_appcontainer_sid", appcontainer_sid)
        return process
    except Exception:
        try:
            policy_path.unlink()
        except OSError:
            pass
        raise


def _os_sandbox_enabled() -> bool:
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
        OS_SANDBOX_POLICY_FILE_ENV,
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
    return resolved


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
) -> tuple[SandboxLaunchPolicy, str]:
    package_sid = _attach_windows_shared_memory_sid(policy, env)
    if package_sid:
        return replace(policy, env=dict(env)), package_sid
    return policy, ""


def _run_child(policy_path: str) -> None:
    with open(policy_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    try:
        Path(policy_path).unlink()
    except OSError:
        pass

    policy = policy_from_payload(payload)
    get_os_sandbox_provider().run(policy)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("sandbox_launcher_policy_required")
    _run_child(sys.argv[1])
