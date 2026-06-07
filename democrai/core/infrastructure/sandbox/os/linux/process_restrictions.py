from __future__ import annotations

import os
import sys
import sysconfig
import tempfile
from typing import Any

from democrai.core.platform.utils.debug import debug_os_sandbox_flow

from .landlock import (
    apply_landlock_filesystem_rules,
    get_landlock_status,
    is_landlock_supported,
)
from .seccomp import apply_seccomp_blocklist, get_seccomp_status, is_seccomp_supported


# --- Config helpers ---

def is_seccomp_enabled(config: Any = None) -> bool:
    resolved = _resolve_config(config)
    getter = getattr(resolved, "get", None)
    if not callable(getter):
        return False
    return bool(getter("sandbox.os.seccomp.enabled", False))


def is_landlock_enabled(config: Any = None) -> bool:
    resolved = _resolve_config(config)
    getter = getattr(resolved, "get", None)
    if not callable(getter):
        return False
    return bool(getter("sandbox.os.landlock.enabled", False))


def _resolve_config(config: Any) -> Any:
    if config is not None:
        return config
    try:
        from democrai.core.runtime.foundation.app import app_ctx
        return app_ctx().config
    except Exception:
        return None


# --- Path collection ---

def _collect_system_read_only_paths() -> list[str]:
    """Paths that the process needs read (+ execute) access to but must not write."""
    candidates: list[str] = [
        "/proc",
        "/sys",
        "/etc",
        "/usr",
        "/lib",
        "/lib32",
        "/lib64",
        "/run",     # runtime sockets (e.g. systemd-resolved)
        "/dev",     # /dev/null, /dev/urandom, /dev/zero
    ]

    # Python runtime paths
    for key in ("stdlib", "platstdlib", "purelib", "platlib", "data", "include", "scripts"):
        p = sysconfig.get_paths().get(key)
        if p:
            candidates.append(p)

    for p in sys.path:
        if p:
            candidates.append(p)

    for attr in ("prefix", "base_prefix", "exec_prefix"):
        p = getattr(sys, attr, None)
        if p:
            candidates.append(p)

    # Application installation directory and runtime modules
    try:
        from democrai.core.runtime.foundation.paths import get_base_dir
        candidates.append(str(get_base_dir()))
    except Exception:
        pass

    try:
        from democrai.core.runtime.foundation.paths import get_runtime_module_dirs
        candidates.extend(get_runtime_module_dirs())
    except Exception:
        pass

    return _dedupe_existing(candidates)


def _collect_app_read_write_paths(config: Any) -> list[str]:
    """Paths the application needs read-write access to."""
    candidates: list[str] = []

    try:
        from democrai.core.runtime.foundation.paths import (
            cache_dir, config_dir, data_dir, logs_dir, state_dir,
        )
        for factory in (data_dir, config_dir, cache_dir, state_dir, logs_dir):
            try:
                candidates.append(str(factory().resolve()))
            except Exception:
                pass
    except Exception:
        pass

    try:
        from democrai.core.runtime.foundation.paths import (
            get_runtime_engine_dirs,
            get_runtime_extractor_dirs,
            get_runtime_module_dirs,
        )
        candidates.extend(get_runtime_module_dirs())
        candidates.extend(get_runtime_engine_dirs())
        candidates.extend(get_runtime_extractor_dirs())
    except Exception:
        pass

    tmp = tempfile.gettempdir()
    if tmp:
        candidates.append(tmp)

    # Media path from config (local storage only)
    if config is not None:
        getter = getattr(config, "get", None)
        if callable(getter):
            media_type = str(getter("storage.media.type", "local") or "local").strip().lower()
            if media_type == "local":
                media_path = getter("storage.media.path")
                if media_path:
                    candidates.append(str(media_path))

    return _dedupe_existing(candidates)


def _extra_config_paths(config: Any, key: str) -> list[str]:
    if config is None:
        return []
    getter = getattr(config, "get", None)
    if not callable(getter):
        return []
    raw = getter(key, []) or []
    return _dedupe_existing([str(p) for p in raw if p])


def _dedupe_existing(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in paths:
        p = str(raw or "").strip()
        if not p:
            continue
        try:
            real = os.path.realpath(p)
        except Exception:
            continue
        if real in seen:
            continue
        seen.add(real)
        if os.path.exists(real):
            result.append(real)
    return result


def build_landlock_path_allowlist(config: Any = None) -> dict[str, list[str]]:
    """Return read_only_paths and read_write_paths for Landlock rule setup.

    Must be called after the media directory has been created (i.e. after
    finalize_setup / ensure_setup_storage_writable) so that all paths exist
    and Landlock can open them with O_PATH.
    """
    resolved = _resolve_config(config)
    ro = _collect_system_read_only_paths()
    ro += _extra_config_paths(resolved, "sandbox.os.landlock.extra_read_paths")

    rw = _collect_app_read_write_paths(resolved)
    rw += _extra_config_paths(resolved, "sandbox.os.landlock.extra_write_paths")

    debug_os_sandbox_flow(
        "process_restrictions.landlock_paths",
        ro_count=len(ro),
        rw_count=len(rw),
    )
    return {"read_only_paths": ro, "read_write_paths": rw}


# --- Main entry point ---

def apply_process_restrictions(config: Any = None) -> dict[str, Any]:
    """Apply seccomp and/or Landlock based on the current config.

    Seccomp: applied unconditionally if enabled (no path dependencies).
    Landlock: applied only when all relevant paths are already on disk —
              call this after setup storage has been initialised.

    Returns a status dict with keys 'seccomp' and 'landlock', each containing
    {'applied': bool, 'skipped': bool, 'error': str | None}.
    """
    resolved = _resolve_config(config)

    result: dict[str, Any] = {
        "seccomp":  {"applied": False, "skipped": True, "error": None},
        "landlock": {"applied": False, "skipped": True, "error": None},
    }

    # --- seccomp ---
    if is_seccomp_enabled(resolved):
        result["seccomp"]["skipped"] = False
        debug_os_sandbox_flow("process_restrictions.seccomp_apply_requested")
        if is_seccomp_supported():
            try:
                apply_seccomp_blocklist()
                result["seccomp"]["applied"] = True
                debug_os_sandbox_flow("process_restrictions.seccomp_applied")
            except Exception as exc:
                result["seccomp"]["error"] = str(exc)
                debug_os_sandbox_flow("process_restrictions.seccomp_failed", error=str(exc))
        else:
            debug_os_sandbox_flow(
                "process_restrictions.seccomp_not_supported",
                **get_seccomp_status(),
            )

    # --- landlock ---
    if is_landlock_enabled(resolved):
        result["landlock"]["skipped"] = False
        debug_os_sandbox_flow("process_restrictions.landlock_apply_requested")
        if is_landlock_supported():
            try:
                paths = build_landlock_path_allowlist(resolved)
                apply_landlock_filesystem_rules(**paths)
                result["landlock"]["applied"] = True
                debug_os_sandbox_flow(
                    "process_restrictions.landlock_applied",
                    ro_count=len(paths["read_only_paths"]),
                    rw_count=len(paths["read_write_paths"]),
                )
            except Exception as exc:
                result["landlock"]["error"] = str(exc)
                debug_os_sandbox_flow("process_restrictions.landlock_failed", error=str(exc))
        else:
            debug_os_sandbox_flow(
                "process_restrictions.landlock_not_supported",
                **get_landlock_status(),
            )

    return result


def get_process_restrictions_status(config: Any = None) -> dict[str, Any]:
    resolved = _resolve_config(config)
    return {
        "seccomp": {
            "enabled": is_seccomp_enabled(resolved),
            **get_seccomp_status(),
        },
        "landlock": {
            "enabled": is_landlock_enabled(resolved),
            **get_landlock_status(),
        },
    }
