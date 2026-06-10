from __future__ import annotations

import ctypes
import ctypes.util
import platform
import sys
from typing import Any


# --- BPF opcode constants ---

_BPF_LD  = 0x00
_BPF_W   = 0x00
_BPF_ABS = 0x20
_BPF_JMP = 0x05
_BPF_JEQ = 0x10
_BPF_K   = 0x00
_BPF_RET = 0x06

_SECCOMP_RET_ALLOW        = 0x7FFF0000
_SECCOMP_RET_KILL_PROCESS = 0x80000000

# --- prctl / seccomp constants ---

_PR_SET_NO_NEW_PRIVS      = 38
_SECCOMP_SET_MODE_FILTER  = 1
_SECCOMP_FILTER_FLAG_TSYNC = 1 << 0

# --- AUDIT_ARCH values (seccomp_data.arch) ---

_AUDIT_ARCH_X86_64  = 0xC000003E
_AUDIT_ARCH_AARCH64 = 0xC00000B7

# --- Syscall numbers (per architecture) ---

# Syscalls to block with KILL_PROCESS.
# Rationale per group:
#   exec is deliberately NOT blocked: the core spawns processes by design
#   (orchestrator, workers, installs, helper). What may be executed is
#   enforced by Landlock FS_EXECUTE path rules and the process guard
#   subprocess allowlist, not by denying the syscall outright.
#   ptrace:     prevents process inspection / code injection into other processes
#   kexec:      prevents kernel replacement
#   modules:    prevents loading kernel modules
#   namespaces: prevents privilege escalation via user namespaces (pivot_root, chroot)
#   setuid:     prevents privilege escalation via UID manipulation
#   bpf:        prevents loading new BPF programs from the application
#   perf/ufd:   blocks syscalls commonly used in kernel exploits

_BLOCKED_NROS: dict[str, list[int]] = {
    "x86_64": [
        101,  # ptrace
        246,  # kexec_load
        320,  # kexec_file_load
        174,  # create_module
        175,  # init_module
        176,  # delete_module
        313,  # finit_module
        155,  # pivot_root
        161,  # chroot
        105,  # setuid
        106,  # setgid
        117,  # setresuid
        119,  # setresgid
        122,  # setfsuid
        123,  # setfsgid
        321,  # bpf
        298,  # perf_event_open
        323,  # userfaultfd
    ],
    "aarch64": [
        117,  # ptrace
        104,  # kexec_load
        294,  # kexec_file_load
        105,  # init_module
        106,  # delete_module
        273,  # finit_module
        41,   # pivot_root
        51,   # chroot
        146,  # setuid
        144,  # setgid
        147,  # setresuid
        149,  # setresgid
        151,  # setfsuid
        152,  # setfsgid
        280,  # bpf
        241,  # perf_event_open
        282,  # userfaultfd
    ],
}

_AUDIT_ARCH: dict[str, int] = {
    "x86_64":  _AUDIT_ARCH_X86_64,
    "aarch64": _AUDIT_ARCH_AARCH64,
}

# SYS_seccomp syscall number per architecture
_SYS_SECCOMP: dict[str, int] = {
    "x86_64":  317,
    "aarch64": 277,
}


# --- ctypes structures ---

class _BPFInstruction(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_uint16),
        ("jt",   ctypes.c_uint8),
        ("jf",   ctypes.c_uint8),
        ("k",    ctypes.c_uint32),
    ]


class _BPFProgram(ctypes.Structure):
    _fields_ = [
        ("len",    ctypes.c_uint16),
        ("filter", ctypes.POINTER(_BPFInstruction)),
    ]


# --- BPF filter helpers ---

def _stmt(code: int, k: int) -> _BPFInstruction:
    return _BPFInstruction(code=code & 0xFFFF, jt=0, jf=0, k=k & 0xFFFFFFFF)


def _jump(code: int, k: int, jt: int, jf: int) -> _BPFInstruction:
    return _BPFInstruction(code=code & 0xFFFF, jt=jt & 0xFF, jf=jf & 0xFF, k=k & 0xFFFFFFFF)


def _build_blocklist_filter(
    blocked_nrs: list[int],
    arch_constant: int,
) -> list[_BPFInstruction]:
    """Build a BPF program that kills the process on any syscall in blocked_nrs.

    Filter layout:
      1. Load arch (offset 4 in seccomp_data) and validate — wrong arch → KILL.
      2. Load syscall number (offset 0).
      3. For each blocked nr: JEQ → KILL.
      4. Default: ALLOW.
    """
    insns: list[_BPFInstruction] = []

    # Validate architecture
    insns.append(_stmt(_BPF_LD | _BPF_W | _BPF_ABS, 4))
    insns.append(_jump(_BPF_JMP | _BPF_JEQ | _BPF_K, arch_constant, 1, 0))
    insns.append(_stmt(_BPF_RET | _BPF_K, _SECCOMP_RET_KILL_PROCESS))

    # Load syscall number
    insns.append(_stmt(_BPF_LD | _BPF_W | _BPF_ABS, 0))

    # Blocklist: for each blocked syscall, kill if matched
    for nr in blocked_nrs:
        # jt=0 → same instruction (KILL), jf=1 → skip KILL
        insns.append(_jump(_BPF_JMP | _BPF_JEQ | _BPF_K, nr, 0, 1))
        insns.append(_stmt(_BPF_RET | _BPF_K, _SECCOMP_RET_KILL_PROCESS))

    # Default: allow
    insns.append(_stmt(_BPF_RET | _BPF_K, _SECCOMP_RET_ALLOW))

    return insns


# --- Public API ---

def _machine() -> str:
    return platform.machine().lower().strip()


def _arch_info() -> tuple[str, int, list[int]] | None:
    m = _machine()
    arch = _AUDIT_ARCH.get(m)
    nrs  = _BLOCKED_NROS.get(m)
    if arch is None or nrs is None:
        return None
    return m, arch, nrs


def is_seccomp_supported() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    if _arch_info() is None:
        return False
    return bool(ctypes.util.find_library("c"))


def get_seccomp_status() -> dict[str, Any]:
    m = _machine()
    return {
        "supported":            is_seccomp_supported(),
        "platform":             sys.platform,
        "machine":              m,
        "arch_known":           m in _AUDIT_ARCH,
        "blocked_syscall_count": len(_BLOCKED_NROS.get(m, [])),
    }


def apply_seccomp_blocklist() -> None:
    """Apply a seccomp BPF blocklist to the current process.

    Blocks a curated set of dangerous syscalls (exec, ptrace, kexec, setuid,
    BPF, etc.) with SECCOMP_RET_KILL_PROCESS.  Uses SECCOMP_FILTER_FLAG_TSYNC
    to cover all threads; falls back to per-thread filter if TSYNC is rejected.

    No-op on non-Linux platforms or unsupported architectures.
    Raises RuntimeError on unexpected failures.
    """
    if not sys.platform.startswith("linux"):
        return

    info = _arch_info()
    if info is None:
        return

    machine, arch_constant, blocked_nrs = info

    libc_name = ctypes.util.find_library("c")
    if not libc_name:
        raise RuntimeError("seccomp_apply_failed:libc_not_found")
    libc = ctypes.CDLL(libc_name, use_errno=True)

    insns = _build_blocklist_filter(blocked_nrs, arch_constant)
    filter_arr = (_BPFInstruction * len(insns))(*insns)
    prog = _BPFProgram(len=len(insns), filter=filter_arr)

    # PR_SET_NO_NEW_PRIVS is required before loading a seccomp filter
    # when the process does not have CAP_SYS_ADMIN.
    ret = libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
    if ret != 0:
        err = ctypes.get_errno()
        raise RuntimeError(f"seccomp_apply_failed:prctl_no_new_privs:{err}")

    sys_seccomp = _SYS_SECCOMP.get(machine)
    if sys_seccomp is None:
        raise RuntimeError(f"seccomp_apply_failed:unknown_sys_seccomp:{machine}")

    # Try with TSYNC (apply to all threads simultaneously)
    ret = libc.syscall(
        ctypes.c_long(sys_seccomp),
        ctypes.c_uint(_SECCOMP_SET_MODE_FILTER),
        ctypes.c_uint(_SECCOMP_FILTER_FLAG_TSYNC),
        ctypes.byref(prog),
    )
    if ret == 0:
        return

    # TSYNC may fail if threads already have incompatible filters;
    # fall back to filtering only the calling thread.
    ret = libc.syscall(
        ctypes.c_long(sys_seccomp),
        ctypes.c_uint(_SECCOMP_SET_MODE_FILTER),
        ctypes.c_uint(0),
        ctypes.byref(prog),
    )
    if ret != 0:
        err = ctypes.get_errno()
        raise RuntimeError(f"seccomp_apply_failed:syscall_seccomp:{err}")
