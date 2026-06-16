"""Windows Filtering Platform (WFP) egress enforcement primitives.

This is the Windows analog of the Linux privileged network helper
(``os/linux/network.py``): instead of cgroup + iptables OUTBOUND chains keyed on
a process's cgroup, it programs WFP filters at the ALE_AUTH_CONNECT layers keyed
on a per-child *identity* (an executable app-id, or a token SID via a security
descriptor). Enforcement happens inside the TCP/IP stack, so — unlike the
in-process ``policy_guard`` monkeypatch — it also catches ``ctypes``/native
sockets and child ``subprocess`` egress.

WFP user-mode has no raw-PID condition. The condition fields available at
``FWPM_LAYER_ALE_AUTH_CONNECT_V4/V6`` are ALE_APP_ID (executable path),
ALE_USER_ID (token, matched via a security descriptor) and ALE_PACKAGE_ID
(AppContainer). The caller supplies an :class:`WfpIdentity` describing which one
to key filters on; everything else here is identity-agnostic.

All filters are added under a DYNAMIC WFP session: when the engine handle closes
(helper exits, or crashes) every filter this process added is removed
automatically — no orphaned system-wide rules.

Requires elevation (the WFP engine cannot be opened for write without it). This
module only builds the primitives; the fail-closed policy lives in the helper
backend.
"""

from __future__ import annotations

import ctypes
import socket
import sys
from ctypes import wintypes
from dataclasses import dataclass

# fwpuclnt returns Win32/HRESULT codes; 0 == ERROR_SUCCESS.
ERROR_SUCCESS = 0
RPC_C_AUTHN_WINNT = 10

FWPM_SESSION_FLAG_DYNAMIC = 0x00000001

# FWP_ACTION_TYPE: BLOCK/PERMIT are terminating (highest-weight terminating
# match in a sublayer decides the sublayer's verdict).
FWP_ACTION_FLAG_TERMINATING = 0x00001000
FWP_ACTION_BLOCK = 0x00000001 | FWP_ACTION_FLAG_TERMINATING
FWP_ACTION_PERMIT = 0x00000002 | FWP_ACTION_FLAG_TERMINATING

# FWP_DATA_TYPE
FWP_UINT8 = 1
FWP_UINT16 = 2
FWP_UINT32 = 3
FWP_BYTE_BLOB_TYPE = 12
FWP_SECURITY_DESCRIPTOR_TYPE = 14
FWP_V4_ADDR_MASK = 0x100
FWP_V6_ADDR_MASK = 0x101

# FWP_MATCH_TYPE
FWP_MATCH_EQUAL = 0

SDDL_REVISION_1 = 1
# Access right WFP checks a token against in an ALE_USER_ID security descriptor.
FWP_ACTRL_MATCH_FILTER = 0x00000001

IPPROTO_TCP = 6
IPPROTO_UDP = 17

# Stable sublayer key for democrai's egress filters (arbitrary fixed GUID).
_DEMOCRAI_SUBLAYER_GUID = "{a3b1f2c4-9d6e-4f1a-8b2c-7e5d4c3b2a10}"

# Well-known WFP GUIDs.
_FWPM_LAYER_ALE_AUTH_CONNECT_V4 = "{c38d57d1-05a7-4c33-904f-7fbceee60e82}"
_FWPM_LAYER_ALE_AUTH_CONNECT_V6 = "{4a72393b-319f-44bc-84c3-ba54dcb3b6b4}"
_FWPM_CONDITION_ALE_APP_ID = "{d78e1e87-8644-4ea5-9437-d809ecefc971}"
_FWPM_CONDITION_ALE_USER_ID = "{af043a0a-b34d-4f86-979c-c90371af6e66}"
_FWPM_CONDITION_IP_REMOTE_ADDRESS = "{b235ae9a-1d64-49b8-a44c-5ff3d9095045}"
_FWPM_CONDITION_IP_REMOTE_PORT = "{c35a604d-d22b-48b1-b4b9-ee7e3d3e5b1e}"
_FWPM_CONDITION_IP_PROTOCOL = "{3971ef2b-623e-4f9a-8cb1-6e79b806b9a7}"

# Filter weights inside our sublayer: PERMIT (loopback/allowlist) must outrank
# the catch-all BLOCK so insertion order never opens a window.
_WEIGHT_BLOCK = 1
_WEIGHT_PERMIT = 10


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def __init__(self, guid_string: str | None = None) -> None:
        super().__init__()
        if guid_string:
            text = guid_string.strip().strip("{}")
            parts = text.split("-")
            self.Data1 = int(parts[0], 16)
            self.Data2 = int(parts[1], 16)
            self.Data3 = int(parts[2], 16)
            tail = parts[3] + parts[4]
            for index in range(8):
                self.Data4[index] = int(tail[index * 2 : index * 2 + 2], 16)


class FWP_BYTE_BLOB(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint32),
        ("data", ctypes.POINTER(ctypes.c_uint8)),
    ]


class FWP_V4_ADDR_AND_MASK(ctypes.Structure):
    _fields_ = [
        ("addr", ctypes.c_uint32),
        ("mask", ctypes.c_uint32),
    ]


class FWP_V6_ADDR_AND_MASK(ctypes.Structure):
    _fields_ = [
        ("addr", ctypes.c_uint8 * 16),
        ("prefixLength", ctypes.c_uint8),
    ]


class _FWP_VALUE_UNION(ctypes.Union):
    _fields_ = [
        ("uint8", ctypes.c_uint8),
        ("uint16", ctypes.c_uint16),
        ("uint32", ctypes.c_uint32),
        ("byteBlob", ctypes.POINTER(FWP_BYTE_BLOB)),
        ("sid", ctypes.c_void_p),
        ("sd", ctypes.POINTER(FWP_BYTE_BLOB)),
        ("v4AddrMask", ctypes.POINTER(FWP_V4_ADDR_AND_MASK)),
        ("v6AddrMask", ctypes.POINTER(FWP_V6_ADDR_AND_MASK)),
    ]


class FWP_VALUE0(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_uint32), ("u", _FWP_VALUE_UNION)]


class FWP_CONDITION_VALUE0(ctypes.Structure):
    # Same layout as FWP_VALUE0 for the subset we use.
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_uint32), ("u", _FWP_VALUE_UNION)]


class FWPM_FILTER_CONDITION0(ctypes.Structure):
    _fields_ = [
        ("fieldKey", GUID),
        ("matchType", ctypes.c_uint32),
        ("conditionValue", FWP_CONDITION_VALUE0),
    ]


class FWPM_DISPLAY_DATA0(ctypes.Structure):
    _fields_ = [
        ("name", wintypes.LPWSTR),
        ("description", wintypes.LPWSTR),
    ]


class FWPM_ACTION0(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("filterType", GUID),
    ]


class _FWPM_FILTER_CONTEXT(ctypes.Union):
    _fields_ = [
        ("rawContext", ctypes.c_uint64),
        ("providerContextKey", GUID),
    ]


class FWPM_FILTER0(ctypes.Structure):
    _anonymous_ = ("context",)
    _fields_ = [
        ("filterKey", GUID),
        ("displayData", FWPM_DISPLAY_DATA0),
        ("flags", ctypes.c_uint32),
        ("providerKey", ctypes.POINTER(GUID)),
        ("providerData", FWP_BYTE_BLOB),
        ("layerKey", GUID),
        ("subLayerKey", GUID),
        ("weight", FWP_VALUE0),
        ("numFilterConditions", ctypes.c_uint32),
        ("filterCondition", ctypes.POINTER(FWPM_FILTER_CONDITION0)),
        ("action", FWPM_ACTION0),
        ("context", _FWPM_FILTER_CONTEXT),
        ("reserved", ctypes.POINTER(GUID)),
        ("filterId", ctypes.c_uint64),
        ("effectiveWeight", FWP_VALUE0),
    ]


class FWPM_SUBLAYER0(ctypes.Structure):
    _fields_ = [
        ("subLayerKey", GUID),
        ("displayData", FWPM_DISPLAY_DATA0),
        ("flags", ctypes.c_uint16),
        ("providerKey", ctypes.POINTER(GUID)),
        ("providerData", FWP_BYTE_BLOB),
        ("weight", ctypes.c_uint16),
    ]


class FWPM_SESSION0(ctypes.Structure):
    _fields_ = [
        ("sessionKey", GUID),
        ("displayData", FWPM_DISPLAY_DATA0),
        ("flags", ctypes.c_uint32),
        ("txnWaitTimeoutInMSec", ctypes.c_uint32),
        ("processId", ctypes.c_uint32),
        ("sid", ctypes.c_void_p),
        ("username", wintypes.LPWSTR),
        ("kernelMode", ctypes.c_int),
    ]


@dataclass(frozen=True)
class WfpIdentity:
    """How to key WFP filters on the sandboxed child.

    ``kind == "app_id"``: ``value`` is the child's executable path (the filter
    matches its ALE_APP_ID). ``kind == "user_id"``: ``value`` is the child's
    string SID (the filter matches its ALE_USER_ID via a security descriptor).
    """

    kind: str
    value: str


@dataclass(frozen=True)
class AllowedEndpoint:
    host_ip: str
    port: int
    protocol: str = "tcp"


def is_process_elevated() -> bool:
    """True if the current process token is elevated (admin).

    WFP write access (FwpmEngineOpen0 + FwpmFilterAdd0) requires elevation; the
    helper backend uses this to fail closed rather than silently no-op.
    """
    if sys.platform != "win32":
        return False
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    token = wintypes.HANDLE()
    _TOKEN_QUERY = 0x0008
    _TOKEN_ELEVATION = 20
    if not advapi32.OpenProcessToken(
        wintypes.HANDLE(-1), _TOKEN_QUERY, ctypes.byref(token)
    ):
        return False
    try:
        elevation = wintypes.DWORD(0)
        size = wintypes.DWORD(0)
        if not advapi32.GetTokenInformation(
            token,
            _TOKEN_ELEVATION,
            ctypes.byref(elevation),
            ctypes.sizeof(elevation),
            ctypes.byref(size),
        ):
            return False
        return bool(elevation.value)
    finally:
        kernel32.CloseHandle(token)


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TH32CS_SNAPPROCESS = 0x00000002


def process_image_path(pid: int) -> str:
    """Full executable image path of ``pid`` (its ALE_APP_ID source).

    The helper resolves a child's WFP identity from its pid via this — the path
    a sandboxed child was launched from is the app-id WFP matches on.
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def _parent_pid_map() -> dict[int, int]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snapshot == wintypes.HANDLE(-1).value or not snapshot:
        raise ctypes.WinError(ctypes.get_last_error())
    mapping: dict[int, int] = {}
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return mapping
        while True:
            mapping[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return mapping


def is_descendant_pid(pid: int, ancestor: int, *, max_depth: int = 64) -> bool:
    """True if ``pid`` is ``ancestor`` or a (transitive) child of it.

    Lineage guard for the helper: only pids in the launching app's process tree
    may have their egress filters applied/cleared (defense-in-depth on top of the
    HMAC client token). Toolhelp parent pids can be reused, so this is best-effort
    and complements — not replaces — the token check.
    """
    pid = int(pid)
    ancestor = int(ancestor)
    if pid == ancestor:
        return True
    parents = _parent_pid_map()
    current = pid
    for _ in range(max_depth):
        parent = parents.get(current)
        if parent is None or parent == current:
            return False
        if parent == ancestor:
            return True
        current = parent
    return False


def _fwpuclnt() -> ctypes.WinDLL:
    return ctypes.WinDLL("fwpuclnt", use_last_error=True)


def _check(code: int, where: str) -> None:
    if int(code) != ERROR_SUCCESS:
        raise OSError(f"{where} failed: 0x{int(code) & 0xFFFFFFFF:08X}")


def _security_descriptor_blob_for_sid(string_sid: str) -> tuple[FWP_BYTE_BLOB, object]:
    """Self-relative SD granting FWP match access to ``string_sid``.

    Returns (blob, keepalive). WFP evaluates an ALE_USER_ID condition by
    access-checking the connecting token against this SD; a child whose token
    carries ``string_sid`` passes, so the filter matches only that child.
    """
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    sddl = f"D:(A;;0x{FWP_ACTRL_MATCH_FILTER:X};;;{string_sid})"
    psd = wintypes.LPVOID()
    size = wintypes.DWORD(0)
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        ctypes.c_wchar_p(sddl),
        SDDL_REVISION_1,
        ctypes.byref(psd),
        ctypes.byref(size),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        raw = ctypes.string_at(psd.value, int(size.value))
    finally:
        kernel32.LocalFree(psd)
    buffer = (ctypes.c_uint8 * len(raw)).from_buffer_copy(raw)
    blob = FWP_BYTE_BLOB(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint8)))
    return blob, buffer


def appid_blob_for_path(path: str) -> tuple[FWP_BYTE_BLOB, object]:
    """ALE_APP_ID byte blob for an executable path, owned by Python.

    ``FwpmGetAppIdFromFileName0`` normalizes the path to the NT device form WFP
    matches on; we copy the bytes into a Python-owned buffer and free WFP's.
    """
    fwpuclnt = _fwpuclnt()
    blob_ptr = ctypes.POINTER(FWP_BYTE_BLOB)()
    _check(
        fwpuclnt.FwpmGetAppIdFromFileName0(
            ctypes.c_wchar_p(str(path)), ctypes.byref(blob_ptr)
        ),
        "FwpmGetAppIdFromFileName0",
    )
    try:
        source = blob_ptr.contents
        raw = ctypes.string_at(source.data, int(source.size))
    finally:
        fwpuclnt.FwpmFreeMemory0(ctypes.byref(blob_ptr))
    buffer = (ctypes.c_uint8 * len(raw)).from_buffer_copy(raw)
    blob = FWP_BYTE_BLOB(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint8)))
    return blob, buffer


class WfpEngine:
    """A dynamic WFP session with democrai's egress sublayer.

    Filters added here vanish when ``close()`` runs or the process dies (dynamic
    session). ``apply_block_except`` installs the per-child rule set; the engine
    tracks the filter ids it created per identity for explicit ``clear``.
    """

    def __init__(self) -> None:
        self._fwpuclnt = _fwpuclnt()
        self._engine = wintypes.HANDLE()
        # identity key -> list[filter id]
        self._filters: dict[str, list[int]] = {}
        # keepalive references for condition buffers, indexed by identity key
        self._keepalive: dict[str, list[object]] = {}

    def open(self) -> None:
        session = FWPM_SESSION0()
        session.flags = FWPM_SESSION_FLAG_DYNAMIC
        session.displayData.name = "democrai os sandbox"
        session.displayData.description = "democrai egress enforcement"
        _check(
            self._fwpuclnt.FwpmEngineOpen0(
                None,
                RPC_C_AUTHN_WINNT,
                None,
                ctypes.byref(session),
                ctypes.byref(self._engine),
            ),
            "FwpmEngineOpen0",
        )
        self._ensure_sublayer()

    def _ensure_sublayer(self) -> None:
        sublayer = FWPM_SUBLAYER0()
        sublayer.subLayerKey = GUID(_DEMOCRAI_SUBLAYER_GUID)
        sublayer.displayData.name = "democrai egress"
        sublayer.displayData.description = "democrai sandbox egress sublayer"
        sublayer.weight = 0x0F00
        code = int(self._fwpuclnt.FwpmSubLayerAdd0(self._engine, ctypes.byref(sublayer), None))
        # FWP_E_ALREADY_EXISTS (0x80320009) is fine — a prior dynamic session in
        # this process, or a leftover, already created it.
        if code not in (ERROR_SUCCESS, 0x80320009):
            _check(code, "FwpmSubLayerAdd0")

    def close(self) -> None:
        if self._engine:
            self._fwpuclnt.FwpmEngineClose0(self._engine)
            self._engine = wintypes.HANDLE()
        self._filters.clear()
        self._keepalive.clear()

    # -- filter construction -------------------------------------------------

    def _identity_condition(
        self, identity: WfpIdentity, keepalive: list[object]
    ) -> FWPM_FILTER_CONDITION0:
        condition = FWPM_FILTER_CONDITION0()
        condition.matchType = FWP_MATCH_EQUAL
        if identity.kind == "app_id":
            condition.fieldKey = GUID(_FWPM_CONDITION_ALE_APP_ID)
            blob, buffer = appid_blob_for_path(identity.value)
            keepalive.extend([blob, buffer])
            condition.conditionValue.type = FWP_BYTE_BLOB_TYPE
            condition.conditionValue.byteBlob = ctypes.pointer(blob)
        elif identity.kind == "user_id":
            condition.fieldKey = GUID(_FWPM_CONDITION_ALE_USER_ID)
            blob, buffer = _security_descriptor_blob_for_sid(identity.value)
            keepalive.extend([blob, buffer])
            condition.conditionValue.type = FWP_SECURITY_DESCRIPTOR_TYPE
            condition.conditionValue.sd = ctypes.pointer(blob)
        else:
            raise ValueError(f"wfp_identity_kind_unsupported:{identity.kind}")
        return condition

    def _add_filter(
        self,
        identity_key: str,
        *,
        layer_guid: str,
        action: int,
        weight: int,
        conditions: list[FWPM_FILTER_CONDITION0],
        keepalive: list[object],
    ) -> None:
        flt = FWPM_FILTER0()
        flt.layerKey = GUID(layer_guid)
        flt.subLayerKey = GUID(_DEMOCRAI_SUBLAYER_GUID)
        flt.displayData.name = "democrai egress filter"
        flt.weight.type = FWP_UINT8
        flt.weight.uint8 = weight
        flt.action.type = action
        condition_array = (FWPM_FILTER_CONDITION0 * len(conditions))(*conditions)
        keepalive.append(condition_array)
        flt.numFilterConditions = len(conditions)
        flt.filterCondition = ctypes.cast(
            condition_array, ctypes.POINTER(FWPM_FILTER_CONDITION0)
        )
        filter_id = ctypes.c_uint64(0)
        _check(
            self._fwpuclnt.FwpmFilterAdd0(
                self._engine, ctypes.byref(flt), None, ctypes.byref(filter_id)
            ),
            "FwpmFilterAdd0",
        )
        self._filters.setdefault(identity_key, []).append(int(filter_id.value))

    def _remote_address_condition_v4(
        self, addr: int, mask: int, keepalive: list[object]
    ) -> FWPM_FILTER_CONDITION0:
        condition = FWPM_FILTER_CONDITION0()
        condition.fieldKey = GUID(_FWPM_CONDITION_IP_REMOTE_ADDRESS)
        condition.matchType = FWP_MATCH_EQUAL
        addr_mask = FWP_V4_ADDR_AND_MASK(addr & 0xFFFFFFFF, mask & 0xFFFFFFFF)
        keepalive.append(addr_mask)
        condition.conditionValue.type = FWP_V4_ADDR_MASK
        condition.conditionValue.v4AddrMask = ctypes.pointer(addr_mask)
        return condition

    def _remote_address_condition_v6(
        self, addr16: bytes, prefix_len: int, keepalive: list[object]
    ) -> FWPM_FILTER_CONDITION0:
        condition = FWPM_FILTER_CONDITION0()
        condition.fieldKey = GUID(_FWPM_CONDITION_IP_REMOTE_ADDRESS)
        condition.matchType = FWP_MATCH_EQUAL
        addr_mask = FWP_V6_ADDR_AND_MASK()
        addr_mask.addr[:] = bytes(addr16)[:16]
        addr_mask.prefixLength = int(prefix_len) & 0xFF
        keepalive.append(addr_mask)
        condition.conditionValue.type = FWP_V6_ADDR_MASK
        condition.conditionValue.v6AddrMask = ctypes.pointer(addr_mask)
        return condition

    def _port_condition(self, port: int) -> FWPM_FILTER_CONDITION0:
        condition = FWPM_FILTER_CONDITION0()
        condition.fieldKey = GUID(_FWPM_CONDITION_IP_REMOTE_PORT)
        condition.matchType = FWP_MATCH_EQUAL
        condition.conditionValue.type = FWP_UINT16
        condition.conditionValue.uint16 = int(port) & 0xFFFF
        return condition

    def _protocol_condition(self, protocol: str) -> FWPM_FILTER_CONDITION0:
        condition = FWPM_FILTER_CONDITION0()
        condition.fieldKey = GUID(_FWPM_CONDITION_IP_PROTOCOL)
        condition.matchType = FWP_MATCH_EQUAL
        condition.conditionValue.type = FWP_UINT8
        condition.conditionValue.uint8 = IPPROTO_UDP if protocol == "udp" else IPPROTO_TCP
        return condition

    # -- public API ----------------------------------------------------------

    def apply_block_except(
        self,
        identity: WfpIdentity,
        *,
        allowed: list[AllowedEndpoint] | None = None,
        loopback: bool = True,
    ) -> None:
        """Block all egress for ``identity`` except loopback + ``allowed``.

        ``allowed`` empty + ``loopback`` True == the ``deny`` policy (only
        loopback IPC reachable). IPv4 carries the resolved allowlist; IPv6 is a
        bridge measure — a catch-all BLOCK plus a ``::1`` loopback PERMIT, so v6
        internet egress is denied while v6 loopback IPC keeps working (the
        per-endpoint v6 allowlist is future work, see the spike).
        """
        identity_key = f"{identity.kind}:{identity.value}".lower()
        keepalive = self._keepalive.setdefault(identity_key, [])

        # Resolve the identity (ALE_APP_ID blob via FwpmGetAppIdFromFileName0, or
        # the ALE_USER_ID security descriptor) ONCE and reuse it across every
        # filter below — _add_filter copies conditions by value into its own
        # array, so the single kept-alive blob safely backs all of them.
        identity_condition = self._identity_condition(identity, keepalive)

        # Catch-all BLOCK for this identity (low weight), on both IP families.
        for layer in (_FWPM_LAYER_ALE_AUTH_CONNECT_V4, _FWPM_LAYER_ALE_AUTH_CONNECT_V6):
            self._add_filter(
                identity_key,
                layer_guid=layer,
                action=FWP_ACTION_BLOCK,
                weight=_WEIGHT_BLOCK,
                conditions=[identity_condition],
                keepalive=keepalive,
            )

        if loopback:
            # 127.0.0.0/8 (v4) + ::1/128 (v6) PERMIT (high weight) so IPC/HTTP/gRPC
            # loopback works over both families.
            self._add_filter(
                identity_key,
                layer_guid=_FWPM_LAYER_ALE_AUTH_CONNECT_V4,
                action=FWP_ACTION_PERMIT,
                weight=_WEIGHT_PERMIT,
                conditions=[
                    identity_condition,
                    self._remote_address_condition_v4(0x7F000000, 0xFF000000, keepalive),
                ],
                keepalive=keepalive,
            )
            self._add_filter(
                identity_key,
                layer_guid=_FWPM_LAYER_ALE_AUTH_CONNECT_V6,
                action=FWP_ACTION_PERMIT,
                weight=_WEIGHT_PERMIT,
                conditions=[
                    identity_condition,
                    self._remote_address_condition_v6(b"\x00" * 15 + b"\x01", 128, keepalive),
                ],
                keepalive=keepalive,
            )

        for endpoint in allowed or ():
            try:
                packed = socket.inet_aton(endpoint.host_ip)
            except OSError:
                continue
            addr = int.from_bytes(packed, "big")
            allow_conditions = [
                identity_condition,
                self._remote_address_condition_v4(addr, 0xFFFFFFFF, keepalive),
                self._port_condition(endpoint.port),
                self._protocol_condition(endpoint.protocol),
            ]
            self._add_filter(
                identity_key,
                layer_guid=_FWPM_LAYER_ALE_AUTH_CONNECT_V4,
                action=FWP_ACTION_PERMIT,
                weight=_WEIGHT_PERMIT,
                conditions=allow_conditions,
                keepalive=keepalive,
            )

    def clear_identity(self, identity: WfpIdentity) -> None:
        identity_key = f"{identity.kind}:{identity.value}".lower()
        for filter_id in self._filters.pop(identity_key, []):
            self._fwpuclnt.FwpmFilterDeleteById0(self._engine, ctypes.c_uint64(filter_id))
        self._keepalive.pop(identity_key, None)
