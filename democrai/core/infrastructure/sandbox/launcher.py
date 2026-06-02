from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from democrai.core.application.access_policy.operations import ResourceType
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

    policy_path = _write_policy(command=command, cwd=cwd, env=env)
    try:
        return subprocess.run(
            [sys.executable, "-m", "democrai.core.infrastructure.sandbox.launcher", str(policy_path)],
            check=bool(check),
            text=bool(text),
            capture_output=bool(capture_output),
            timeout=timeout,
            env=env,
        )
    finally:
        try:
            policy_path.unlink()
        except OSError:
            pass


def _os_sandbox_enabled() -> bool:
    config = getattr(app_ctx(), "config", None)
    getter = getattr(config, "get", None)
    if not callable(getter):
        return False
    return bool(getter("sandbox.os.enabled", False))


def _write_policy(
    *,
    command: list[str],
    cwd: str | None,
    env: dict[str, str] | None,
) -> Path:
    from democrai.core.infrastructure.sandbox import process_guard as process_guard_mod

    state = dict(process_guard_mod._state())
    access = []
    for rule in tuple(state.get("access") or ()):
        if hasattr(rule, "to_dict"):
            access.append(rule.to_dict())

    payload = {
        "command": command,
        "cwd": cwd,
        "env": env,
        "access": access,
    }
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


def _apply_child_filesystem_rules(access: list[dict[str, Any]]) -> None:
    if not sys.platform.startswith("linux"):
        return

    from democrai.core.infrastructure.sandbox.os.landlock import (
        apply_landlock_filesystem_rules,
        is_landlock_supported,
    )

    if not is_landlock_supported():
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None:
            logger.warning(
                "[Sandbox] Landlock is not supported on this system. Filesystem access rules will be ignored."
            )
        return

    read_only_paths: list[str] = []
    read_write_paths: list[str] = []
    for item in access:
        resource = item.get("resource") if isinstance(item, dict) else None
        if not isinstance(resource, dict):
            continue
        if resource.get("resource_type") != ResourceType.FILESYSTEM.value:
            continue
        target = str(resource.get("target") or "").strip()
        if not target:
            continue
        operation = str(resource.get("operation") or "").strip()
        if operation in {"create", "modify", "delete"}:
            read_write_paths.append(target)
        elif operation in {"read", "execute"}:
            read_only_paths.append(target)

    if not read_only_paths and not read_write_paths:
        return

    apply_landlock_filesystem_rules(
        read_only_paths=read_only_paths,
        read_write_paths=read_write_paths,
    )


def _run_child(policy_path: str) -> None:
    with open(policy_path, "r", encoding="utf-8") as handle:
        policy = json.load(handle)
    try:
        Path(policy_path).unlink()
    except OSError:
        pass

    command = policy["command"]
    cwd = policy.get("cwd")
    env = policy.get("env") or os.environ.copy()
    _apply_child_filesystem_rules(list(policy.get("access") or []))
    if cwd is not None:
        os.chdir(str(cwd))
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("sandbox_launcher_policy_required")
    _run_child(sys.argv[1])
