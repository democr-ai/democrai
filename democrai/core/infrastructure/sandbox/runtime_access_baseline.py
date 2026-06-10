from __future__ import annotations

import os
import site
import sys
import sysconfig

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.infrastructure.sandbox.platform_policy import platform_key


_NATIVE_LIBRARY_READ_PATHS_BY_OS = {
    "linux": (
        "/etc/ld.so.cache",
        "/etc/ld.so.conf",
        "/etc/ld.so.conf.d",
    ),
    "darwin": (),
    "win32": (),
}

_LDCONFIG_EXECUTE_PATHS_BY_OS = {
    "linux": (
        "/sbin/ldconfig",
        "/usr/sbin/ldconfig",
    ),
    "darwin": (),
    "win32": (),
}

_GPU_DEVICE_READ_PATHS_BY_OS = {
    "linux": (
        "/dev/null",
        "/dev/nvidiactl",
        "/dev/nvidia0",
        "/dev/nvidia-uvm",
        "/dev/nvidia-uvm-tools",
        "/dev/nvidia-modeset",
    ),
    "darwin": ("/dev/null",),
    "win32": (),
}

_GPU_DEVICE_MODIFY_PATHS_BY_OS = {
    "linux": (
        "/dev/null",
        "/dev/nvidiactl",
        "/dev/nvidia0",
        "/dev/nvidia-uvm",
        "/dev/nvidia-uvm-tools",
        "/dev/nvidia-modeset",
    ),
    "darwin": ("/dev/null",),
    "win32": (),
}

_LIBCUDA_CANDIDATE_PATHS_BY_OS = {
    "linux": (
        "/usr/lib/x86_64-linux-gnu/libcuda.so.1",
        "/usr/lib64/libcuda.so.1",
        "/usr/lib/wsl/lib/libcuda.so.1",
        "/usr/local/cuda/compat/libcuda.so.1",
    ),
    "darwin": (),
    "win32": (),
}

# Native runtimes (CUDA, torch, OpenMP) write to their own /proc entries —
# notably /proc/self/task/<tid>/comm to name worker threads. Without write
# access cuInit fails with "OS call failed" (error 304). /proc is already
# readable; the writable surface here is the process's own tree, and the
# kernel still guards the sensitive entries (procfs write perms, plus the
# seccomp blocklist).
_PROCESS_SELF_WRITE_PATHS_BY_OS = {
    "linux": ("/proc",),
    "darwin": (),
    "win32": (),
}


class RuntimeAccessBaseline:
    """Single source of the access baseline every sandboxed worker needs.

    Covers the Python runtime import path (interpreter chain, prefixes,
    site/sysconfig dirs), the native loader configuration and the GPU device
    nodes. Both sides of a worker launch consume it — the spawn-side landlock
    rules and the worker-side process-guard rules — and so do the engine and
    extractor twins, so the path sets cannot drift between them.

    Path methods are computed in the calling process: the worker recomputes
    them under its own venv interpreter, which is why the worker-side rules
    cannot be precomputed at spawn time.
    """

    @staticmethod
    def python_runtime_read_paths() -> tuple[str, ...]:
        paths: list[str] = []
        try:
            paths.extend(str(item) for item in site.getsitepackages())
        except Exception:
            pass
        try:
            paths.append(str(site.getusersitepackages()))
        except Exception:
            pass
        if sys.platform == "darwin":
            home = str(os.environ.get("HOME") or "").strip()
            if home:
                version = f"{sys.version_info.major}.{sys.version_info.minor}"
                paths.append(
                    os.path.join(
                        home,
                        "Library",
                        "Python",
                        version,
                        "lib",
                        "python",
                        "site-packages",
                    )
                )
        try:
            paths.extend(str(item) for item in sysconfig.get_paths().values())
        except Exception:
            pass
        return tuple(dict.fromkeys(path for path in paths if path))

    @staticmethod
    def python_runtime_execute_paths() -> tuple[str, ...]:
        from democrai.core.infrastructure.sandbox.process_guard import (
            process_guard_bypass_context,
        )

        with process_guard_bypass_context():
            paths: list[str] = []
            executable = str(sys.executable or "").strip()
            if executable:
                paths.extend(_executable_path_chain(executable))
            for raw in (
                sys.prefix,
                sys.exec_prefix,
                sys.base_prefix,
                sys.base_exec_prefix,
            ):
                if isinstance(raw, str) and raw.strip():
                    paths.extend(_path_variants(raw))
            return tuple(dict.fromkeys(path for path in paths if path))

    @staticmethod
    def native_library_read_paths(os_name: str | None = None) -> tuple[str, ...]:
        return _NATIVE_LIBRARY_READ_PATHS_BY_OS.get(os_name or platform_key(), ())

    @staticmethod
    def ldconfig_execute_paths(os_name: str | None = None) -> tuple[str, ...]:
        return _LDCONFIG_EXECUTE_PATHS_BY_OS.get(os_name or platform_key(), ())

    @staticmethod
    def gpu_device_read_paths(os_name: str | None = None) -> tuple[str, ...]:
        return _GPU_DEVICE_READ_PATHS_BY_OS.get(os_name or platform_key(), ())

    @staticmethod
    def gpu_device_modify_paths(os_name: str | None = None) -> tuple[str, ...]:
        return _GPU_DEVICE_MODIFY_PATHS_BY_OS.get(os_name or platform_key(), ())

    @staticmethod
    def libcuda_candidate_paths(os_name: str | None = None) -> tuple[str, ...]:
        return _LIBCUDA_CANDIDATE_PATHS_BY_OS.get(os_name or platform_key(), ())

    @staticmethod
    def process_self_write_paths(os_name: str | None = None) -> tuple[str, ...]:
        return _PROCESS_SELF_WRITE_PATHS_BY_OS.get(os_name or platform_key(), ())

    @classmethod
    def python_runtime_rules(
        cls,
        *,
        subject_kind: str,
        subject_name: str,
    ) -> tuple[AccessManifestRule, ...]:
        """Guard rules for running Python with native extensions.

        Read access to every import-path dir (namespace packages scan all of
        ``sys.path``) and to the native loader configuration, plus
        read+execute on the interpreter chain and prefixes.
        """
        subject = AccessSubject.create(subject_kind, subject_name)
        rules: list[AccessManifestRule] = [
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="read",
                    target=path,
                ),
            )
            for path in (
                *cls.python_runtime_read_paths(),
                *cls.native_library_read_paths(),
            )
        ]
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation=operation,
                    target=path,
                ),
            )
            for path in cls.python_runtime_execute_paths()
            for operation in ("read", "execute")
        )
        return tuple(rules)


def _executable_path_chain(path: str) -> tuple[str, ...]:
    items: list[str] = []
    current = os.path.abspath(os.path.expanduser(path))
    seen: set[str] = set()
    for _ in range(16):
        if current in seen:
            break
        seen.add(current)
        items.extend(_path_variants(current))
        parent = os.path.dirname(current)
        if parent:
            items.extend(_path_variants(parent))
        try:
            if not os.path.islink(current):
                break
            target = os.readlink(current)
        except OSError:
            break
        current = (
            target
            if os.path.isabs(target)
            else os.path.abspath(os.path.join(parent, target))
        )
    return tuple(dict.fromkeys(item for item in items if item))


def _path_variants(path: object) -> tuple[str, ...]:
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
        if real:
            variants.append(real)
    except Exception:
        pass
    return tuple(dict.fromkeys(item for item in variants if item))
