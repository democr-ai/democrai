from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from democrai.core.infrastructure.sandbox.os.base import (
    BaseOsSandboxProvider,
    OsSandboxCapabilities,
)
from democrai.core.infrastructure.sandbox.os.launch_policy import (
    NETWORK_ALLOW_ALL,
    NETWORK_DENY,
    NETWORK_PROXY,
    SandboxLaunchPolicy,
)
from democrai.core.runtime.foundation.paths import state_dir


class MacOSOsSandboxProvider(BaseOsSandboxProvider):
    def capabilities(self) -> OsSandboxCapabilities:
        return OsSandboxCapabilities(
            filesystem=True,
            network_deny=True,
            network_proxy=False,
            network_allow_all=True,
            execute=True,
        )

    def supports(self, policy: SandboxLaunchPolicy) -> bool:
        return super().supports(policy)

    def prepare(self, policy: SandboxLaunchPolicy) -> SandboxLaunchPolicy:
        if policy.network_mode == NETWORK_PROXY:
            raise RuntimeError("macos_sandbox_proxy_unenforceable")
        if not self.supports(policy):
            raise RuntimeError("macos_sandbox_policy_not_supported")
        executable = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        if not os.path.exists(executable):
            raise RuntimeError("macos_sandbox_exec_unavailable")
        return policy

    def apply_current_process(
        self,
        policy: SandboxLaunchPolicy,
        env: dict[str, str],
    ) -> None:
        return

    def exec(self, policy: SandboxLaunchPolicy, env: dict[str, str]) -> None:
        executable = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        profile = seatbelt_profile(policy, proxy_url=_proxy_url_from_env(env))
        profile_path = write_seatbelt_profile(profile)
        if policy.cwd is not None:
            os.chdir(str(policy.cwd))
        os.execvpe(
            executable,
            [executable, "-f", str(profile_path), "--", *policy.command],
            env,
        )


def seatbelt_profile(policy: SandboxLaunchPolicy, *, proxy_url: str = "") -> str:
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process*)",
        "(allow sysctl-read)",
        "(allow file-read-metadata)",
        "(allow ipc-posix-shm*)",
    ]
    if policy.network_mode == NETWORK_ALLOW_ALL:
        lines.append("(allow network*)")
    elif policy.network_mode == NETWORK_PROXY:
        host, port = _loopback_proxy_endpoint(proxy_url)
        lines.append(f"(allow network-outbound (remote tcp {json.dumps(f'{host}:{port}')}))")
    elif policy.network_mode == NETWORK_DENY:
        lines.append("(deny network*)")
    for item in policy.filesystem_access:
        path = json.dumps(str(item.target))
        if item.operation == "read":
            lines.append(f"(allow file-read* (subpath {path}))")
        elif item.operation == "execute":
            lines.append(f"(allow file-read* (literal {path}))")
            lines.append(f"(allow file-read* (subpath {path}))")
        elif item.operation in {"create", "modify", "delete"}:
            lines.append(f"(allow file-read* file-write* (subpath {path}))")
    return "\n".join(lines) + "\n"


def write_seatbelt_profile(profile: str) -> Path:
    cleanup_stale_seatbelt_profiles()
    directory = state_dir() / "os_sandbox" / "seatbelt"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"profile_{os.getpid()}_{uuid.uuid4().hex}.sb"
    path.write_text(profile, encoding="utf-8")
    return path


def cleanup_stale_seatbelt_profiles(*, max_age_seconds: int = 86400) -> None:
    directory = state_dir() / "os_sandbox" / "seatbelt"
    if not directory.exists():
        return
    now = time.time()
    for path in directory.glob("profile_*.sb"):
        try:
            if now - path.stat().st_mtime < int(max_age_seconds):
                continue
            path.unlink()
        except OSError:
            pass


def _proxy_url_from_env(env: dict[str, str]) -> str:
    return str(env.get("ALL_PROXY") or env.get("all_proxy") or "").strip()


def _loopback_proxy_endpoint(proxy_url: str) -> tuple[str, int]:
    parsed = urlparse(str(proxy_url or "").strip())
    host = str(parsed.hostname or "").strip().lower()
    port = int(parsed.port or 0)
    if host == "localhost":
        host = "127.0.0.1"
    if host not in {"127.0.0.1", "::1"} or port <= 0:
        raise RuntimeError("macos_sandbox_proxy_unenforceable")
    return host, port
