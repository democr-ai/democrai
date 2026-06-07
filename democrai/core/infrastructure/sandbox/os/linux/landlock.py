from __future__ import annotations

import ctypes
import ctypes.util
import os
import stat
import sys
from typing import Any


# --- Landlock syscall numbers (same on all architectures, kernel ≥ 5.13) ---

_SYS_LANDLOCK_CREATE_RULESET = 444
_SYS_LANDLOCK_ADD_RULE       = 445
_SYS_LANDLOCK_RESTRICT_SELF  = 446

# --- Landlock constants ---

_LANDLOCK_RULE_PATH_BENEATH       = 1
_LANDLOCK_CREATE_RULESET_VERSION  = 1 << 0  # probe flag to read ABI version

# --- Filesystem access rights ---
# ABI v1 (kernel 5.13)
_LANDLOCK_ACCESS_FS_EXECUTE     = 1 << 0
_LANDLOCK_ACCESS_FS_WRITE_FILE  = 1 << 1
_LANDLOCK_ACCESS_FS_READ_FILE   = 1 << 2
_LANDLOCK_ACCESS_FS_READ_DIR    = 1 << 3
_LANDLOCK_ACCESS_FS_REMOVE_DIR  = 1 << 4
_LANDLOCK_ACCESS_FS_REMOVE_FILE = 1 << 5
_LANDLOCK_ACCESS_FS_MAKE_CHAR   = 1 << 6
_LANDLOCK_ACCESS_FS_MAKE_DIR    = 1 << 7
_LANDLOCK_ACCESS_FS_MAKE_REG    = 1 << 8
_LANDLOCK_ACCESS_FS_MAKE_SOCK   = 1 << 9
_LANDLOCK_ACCESS_FS_MAKE_FIFO   = 1 << 10
_LANDLOCK_ACCESS_FS_MAKE_BLOCK  = 1 << 11
_LANDLOCK_ACCESS_FS_MAKE_SYM    = 1 << 12
# ABI v2 (kernel 5.19)
_LANDLOCK_ACCESS_FS_REFER       = 1 << 13
# ABI v3 (kernel 6.2)
_LANDLOCK_ACCESS_FS_TRUNCATE    = 1 << 14
# ABI v5
_LANDLOCK_ACCESS_FS_IOCTL_DEV   = 1 << 15

_ALL_ACCESS_V1 = (
    _LANDLOCK_ACCESS_FS_EXECUTE
    | _LANDLOCK_ACCESS_FS_WRITE_FILE
    | _LANDLOCK_ACCESS_FS_READ_FILE
    | _LANDLOCK_ACCESS_FS_READ_DIR
    | _LANDLOCK_ACCESS_FS_REMOVE_DIR
    | _LANDLOCK_ACCESS_FS_REMOVE_FILE
    | _LANDLOCK_ACCESS_FS_MAKE_CHAR
    | _LANDLOCK_ACCESS_FS_MAKE_DIR
    | _LANDLOCK_ACCESS_FS_MAKE_REG
    | _LANDLOCK_ACCESS_FS_MAKE_SOCK
    | _LANDLOCK_ACCESS_FS_MAKE_FIFO
    | _LANDLOCK_ACCESS_FS_MAKE_BLOCK
    | _LANDLOCK_ACCESS_FS_MAKE_SYM
)

_READ_ONLY_ACCESS = (
    _LANDLOCK_ACCESS_FS_EXECUTE
    | _LANDLOCK_ACCESS_FS_READ_FILE
    | _LANDLOCK_ACCESS_FS_READ_DIR
)

_PR_SET_NO_NEW_PRIVS = 38

# open(2) flags needed to obtain a parent_fd for Landlock rules
_O_PATH    = 0o10000000
_O_CLOEXEC = 0o2000000


# --- ctypes structures ---

class _RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _PathBeneathAttr(ctypes.Structure):
    """Must be packed — no padding between allowed_access and parent_fd."""
    _pack_ = 1
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd",      ctypes.c_int32),
    ]


# --- Internal helpers ---

def _libc() -> ctypes.CDLL:
    name = ctypes.util.find_library("c")
    if not name:
        raise RuntimeError("landlock_failed:libc_not_found")
    return ctypes.CDLL(name, use_errno=True)


def _syscall(libc: ctypes.CDLL, nr: int, *args: Any) -> int:
    return int(libc.syscall(ctypes.c_long(nr), *args))


def _all_access_for_abi(abi: int) -> int:
    rights = _ALL_ACCESS_V1
    if abi >= 2:
        rights |= _LANDLOCK_ACCESS_FS_REFER
    if abi >= 3:
        rights |= _LANDLOCK_ACCESS_FS_TRUNCATE
    if abi >= 5:
        rights |= _LANDLOCK_ACCESS_FS_IOCTL_DEV
    return rights


def _file_access_for_abi(abi: int, *, write: bool) -> int:
    rights = _LANDLOCK_ACCESS_FS_EXECUTE | _LANDLOCK_ACCESS_FS_READ_FILE
    if write:
        rights |= _LANDLOCK_ACCESS_FS_WRITE_FILE
        if abi >= 3:
            rights |= _LANDLOCK_ACCESS_FS_TRUNCATE
        if abi >= 5:
            rights |= _LANDLOCK_ACCESS_FS_IOCTL_DEV
    return rights


# --- Public API ---

def get_landlock_abi_version() -> int:
    """Return the Landlock ABI version supported by the running kernel, or 0."""
    if not sys.platform.startswith("linux"):
        return 0
    try:
        lib = _libc()
        ret = _syscall(
            lib,
            _SYS_LANDLOCK_CREATE_RULESET,
            ctypes.c_void_p(None),
            ctypes.c_size_t(0),
            ctypes.c_uint32(_LANDLOCK_CREATE_RULESET_VERSION),
        )
        return int(ret) if ret > 0 else 0
    except Exception:
        return 0


def is_landlock_supported() -> bool:
    return get_landlock_abi_version() >= 1


def get_landlock_status() -> dict[str, Any]:
    abi = get_landlock_abi_version()
    return {
        "supported":   abi >= 1,
        "abi_version": abi,
        "platform":    sys.platform,
    }


def apply_landlock_filesystem_rules(
    *,
    read_only_paths: list[str],
    read_write_paths: list[str],
) -> None:
    """Apply Landlock filesystem rules to the current process.

    After this call the process (and all future children) can only access
    paths explicitly listed in read_only_paths or read_write_paths.
    Paths that do not exist at call time are silently skipped.

    This call is irrevocable — the ruleset cannot be relaxed afterward.
    Raises RuntimeError if Landlock is not supported or restriction fails.
    """
    if not sys.platform.startswith("linux"):
        return

    abi = get_landlock_abi_version()
    if abi < 1:
        raise RuntimeError("landlock_not_supported:abi_version_0")

    lib = _libc()
    all_access = _all_access_for_abi(abi)
    rw_access  = all_access
    ro_access  = _READ_ONLY_ACCESS

    ruleset_attr = _RulesetAttr(handled_access_fs=all_access)
    ruleset_fd = _syscall(
        lib,
        _SYS_LANDLOCK_CREATE_RULESET,
        ctypes.byref(ruleset_attr),
        ctypes.c_size_t(ctypes.sizeof(ruleset_attr)),
        ctypes.c_uint32(0),
    )
    if ruleset_fd < 0:
        err = ctypes.get_errno()
        raise RuntimeError(f"landlock_create_ruleset_failed:{err}")

    try:
        for path, access, required in [
            *[(p, ro_access, False) for p in read_only_paths],
            *[(p, rw_access, True) for p in read_write_paths],
        ]:
            resolved = str(path or "").strip()
            if not resolved:
                continue
            try:
                real = os.path.realpath(resolved)
            except Exception as exc:
                if required:
                    raise RuntimeError(
                        f"landlock_path_realpath_failed:{resolved}:{exc}"
                    ) from exc
                continue
            if not os.path.exists(real):
                continue
            try:
                fd = os.open(real, _O_PATH | _O_CLOEXEC)
            except OSError as exc:
                if required:
                    raise RuntimeError(
                        f"landlock_path_open_failed:{real}:{exc.errno}"
                    ) from exc
                continue
            try:
                try:
                    mode = os.stat(real).st_mode
                except OSError as exc:
                    if required:
                        raise RuntimeError(
                            f"landlock_path_stat_failed:{real}:{exc.errno}"
                        ) from exc
                    continue
                allowed_access = (
                    access
                    if stat.S_ISDIR(mode)
                    else _file_access_for_abi(abi, write=required)
                )
                attr = _PathBeneathAttr(allowed_access=allowed_access, parent_fd=fd)
                ret = _syscall(
                    lib,
                    _SYS_LANDLOCK_ADD_RULE,
                    ctypes.c_int(ruleset_fd),
                    ctypes.c_int(_LANDLOCK_RULE_PATH_BENEATH),
                    ctypes.byref(attr),
                    ctypes.c_uint32(0),
                )
                if ret < 0 and required:
                    err = ctypes.get_errno()
                    raise RuntimeError(f"landlock_add_rule_failed:{real}:{err}")
            finally:
                os.close(fd)

        # PR_SET_NO_NEW_PRIVS is required when the process lacks CAP_SYS_ADMIN.
        lib.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)

        ret = _syscall(
            lib,
            _SYS_LANDLOCK_RESTRICT_SELF,
            ctypes.c_int(ruleset_fd),
            ctypes.c_uint32(0),
        )
        if ret < 0:
            err = ctypes.get_errno()
            raise RuntimeError(f"landlock_restrict_self_failed:{err}")

    finally:
        os.close(ruleset_fd)
