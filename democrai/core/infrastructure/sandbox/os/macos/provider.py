from __future__ import annotations

import json
import os
import shutil
import tempfile
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


_MACOS_BASELINE_READ_PATHS = (
    "/System",
    "/System/Volumes/Preboot/Cryptexes/OS",
    "/System/Cryptexes/OS",
    "/Library",
    "/usr/lib",
    "/usr/libexec",
    "/usr/share",
    "/private/etc",
    "/private/var/db/dyld",
    "/private/var/db/timezone",
)

_MACOS_BASELINE_DEVICE_PATHS = (
    "/dev/null",
    "/dev/zero",
    "/dev/random",
    "/dev/urandom",
)

_MACOS_OPTIONAL_RUNTIME_READ_PATHS = (
    "/opt/homebrew",
    "/Library/Frameworks/Python.framework",
)

_PROTECTED_HOME_NAMES = (
    ".aws",
    ".azure",
    ".config",
    ".docker",
    ".gnupg",
    ".kube",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".ssh",
)


class MacOSOsSandboxProvider(BaseOsSandboxProvider):
    def capabilities(self) -> OsSandboxCapabilities:
        return OsSandboxCapabilities(
            filesystem=True,
            network_deny=True,
            network_proxy=True,
            network_allow_all=True,
            execute=True,
        )

    def supports(self, policy: SandboxLaunchPolicy) -> bool:
        return super().supports(policy)

    def prepare(self, policy: SandboxLaunchPolicy) -> SandboxLaunchPolicy:
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
        '(allow file-read* (subpath "/"))',
        "(allow ipc-posix-shm*)",
        '(allow mach-lookup (global-name "com.apple.system.notification_center"))',
        '(allow mach-lookup (global-name "com.apple.logd"))',
    ]
    for path in _macos_baseline_read_paths():
        lines.append(f"(allow file-read* (subpath {_seatbelt_path(path)}))")
    for path in _MACOS_BASELINE_DEVICE_PATHS:
        lines.append(f"(allow file-read* file-write* (literal {_seatbelt_path(path)}))")
    if policy.network_mode == NETWORK_ALLOW_ALL:
        lines.append("(allow network*)")
    elif policy.network_mode == NETWORK_PROXY:
        host, port = _loopback_proxy_endpoint(proxy_url)
        target = json.dumps(f"{_seatbelt_host(host)}:{port}")
        lines.append("(allow network*)")
        lines.append('(deny network-outbound (remote tcp "*:*"))')
        lines.append(f"(allow network-outbound (remote tcp {target}))")
    elif policy.network_mode == NETWORK_DENY:
        lines.append("(allow network*)")
        lines.append('(deny network-outbound (remote tcp "*:*"))')
    for item in policy.filesystem_access:
        if item.operation == "read":
            for path in _seatbelt_path_variants(item.target):
                lines.append(f"(allow file-read* (subpath {path}))")
        elif item.operation == "execute":
            for path in _seatbelt_path_variants(item.target):
                lines.append(f"(allow file-read* (literal {path}))")
                lines.append(f"(allow file-read* (subpath {path}))")
        elif item.operation in {"create", "modify", "delete"}:
            for path in _seatbelt_path_variants(item.target):
                lines.append(f"(allow file-read* file-write* (subpath {path}))")
    for path in _macos_policy_sibling_denied_paths(policy):
        for denied in _seatbelt_path_variants(path):
            lines.append(f"(deny file-read* file-write* (subpath {denied}))")
    for path in _macos_home_protected_denied_paths(policy):
        for denied in _seatbelt_path_variants(path):
            lines.append(f"(deny file-read* file-write* (subpath {denied}))")
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


def _macos_baseline_read_paths() -> tuple[str, ...]:
    paths: list[str] = list(_MACOS_BASELINE_READ_PATHS)
    for raw in _MACOS_OPTIONAL_RUNTIME_READ_PATHS:
        path = Path(raw)
        try:
            if path.exists():
                paths.append(str(path))
        except OSError:
            continue
    return _dedupe_paths(paths)


def _macos_home_protected_denied_paths(policy: SandboxLaunchPolicy) -> tuple[str, ...]:
    home = _macos_home_path()
    if home is None:
        return ()
    denied: list[str] = []
    try:
        candidates = [item for item in home.iterdir() if item.name.startswith(".")]
    except OSError:
        candidates = []
    candidates.extend(home / name for name in _PROTECTED_HOME_NAMES)
    for candidate in candidates:
        try:
            if not candidate.exists() or _policy_touches_path(policy, candidate):
                continue
            denied.append(str(candidate))
        except OSError:
            continue
    return _dedupe_paths(denied)


def _macos_policy_sibling_denied_paths(policy: SandboxLaunchPolicy) -> tuple[str, ...]:
    by_parent: dict[str, set[str]] = {}
    for access in policy.filesystem_access:
        if _is_runtime_filesystem_access(access):
            continue
        target = _canonical_compare_path(access.target)
        parent = os.path.dirname(target)
        if not parent:
            continue
        by_parent.setdefault(parent, set()).add(target)

    denied: list[str] = []
    for parent, approved in by_parent.items():
        if len(approved) < 2:
            continue
        if not _macos_sibling_subtraction_parent_allowed(parent):
            continue
        try:
            entries = tuple(Path(parent).iterdir())
        except OSError:
            continue
        for entry in entries:
            target = _canonical_compare_path(entry)
            if any(_paths_overlap(allowed, target) for allowed in approved):
                continue
            if _subject_policy_touches_path(policy, entry):
                continue
            denied.append(str(entry))
    return _dedupe_paths(denied)


def _is_runtime_filesystem_access(access) -> bool:
    return (
        str(getattr(access, "subject_kind", "") or "").strip() == "core"
        and str(getattr(access, "subject", "") or "").strip()
        == "process_guard_runtime"
    )


def _macos_sibling_subtraction_parent_allowed(parent: str) -> bool:
    try:
        temp_root = _canonical_compare_path(Path(tempfile.gettempdir()))
    except Exception:
        return False
    resolved = _canonical_compare_path(parent)
    return resolved == temp_root or resolved.startswith(temp_root + os.sep)


def _macos_home_path() -> Path | None:
    raw_home = str(os.environ.get("HOME") or "").strip()
    try:
        home = Path(raw_home).expanduser() if raw_home else Path.home()
    except Exception:
        return None
    if not str(home):
        return None
    return home


def _dedupe_paths(paths: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        path = str(raw or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        result.append(path)
    return tuple(result)


def _seatbelt_path(path: object) -> str:
    return json.dumps(str(path))


def _seatbelt_path_variants(path: object) -> tuple[str, ...]:
    raw = str(path or "").strip()
    if not raw:
        return ()
    variants: list[str] = []
    try:
        variants.append(os.path.normpath(os.path.abspath(os.path.expanduser(raw))))
    except Exception:
        variants.append(raw)
    try:
        real = os.path.normpath(os.path.realpath(os.path.expanduser(raw)))
        variants.append(real)
    except Exception:
        pass
    return tuple(_seatbelt_path(item) for item in _dedupe_paths(variants))


def _policy_allows_path(policy: SandboxLaunchPolicy, path: Path) -> bool:
    target = _canonical_compare_path(path)
    for access in policy.filesystem_access:
        if _path_covers(_canonical_compare_path(access.target), target):
            return True
    return False


def _policy_touches_path(policy: SandboxLaunchPolicy, path: Path) -> bool:
    target = _canonical_compare_path(path)
    for access in policy.filesystem_access:
        access_target = _canonical_compare_path(access.target)
        if _paths_overlap(access_target, target):
            return True
    return False


def _subject_policy_touches_path(policy: SandboxLaunchPolicy, path: Path) -> bool:
    target = _canonical_compare_path(path)
    for access in policy.filesystem_access:
        if _is_runtime_filesystem_access(access):
            continue
        access_target = _canonical_compare_path(access.target)
        if _paths_overlap(access_target, target):
            return True
    return False


def _canonical_compare_path(path: object) -> str:
    raw = str(path or "").strip()
    try:
        return os.path.normpath(os.path.realpath(os.path.abspath(os.path.expanduser(raw))))
    except Exception:
        return os.path.normpath(os.path.abspath(os.path.expanduser(raw)))


def _path_covers(parent: str, child: str) -> bool:
    return child == parent or child.startswith(parent + os.sep)


def _paths_overlap(left: str, right: str) -> bool:
    return _path_covers(left, right) or _path_covers(right, left)


def _loopback_proxy_endpoint(proxy_url: str) -> tuple[str, int]:
    parsed = urlparse(str(proxy_url or "").strip())
    host = str(parsed.hostname or "").strip().lower()
    port = int(parsed.port or 0)
    if host == "localhost":
        host = "127.0.0.1"
    if host not in {"127.0.0.1", "::1"} or port <= 0:
        raise RuntimeError("macos_sandbox_proxy_unenforceable")
    return host, port


def _seatbelt_host(host: str) -> str:
    resolved = str(host or "").strip().lower()
    if resolved in {"127.0.0.1", "::1", "localhost"}:
        return "localhost"
    return resolved

