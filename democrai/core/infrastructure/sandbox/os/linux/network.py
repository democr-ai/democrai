from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from democrai.core.platform.utils.debug import debug_os_sandbox_flow

from democrai.core.infrastructure.sandbox.os.models import (
    ApplicationNetworkAllowlist,
    NetworkEndpoint,
)


_CGROUP_ROOT = Path("/sys/fs/cgroup")
_CGROUP_PREFIX = "democrai_os_sandbox"
_IPTABLES = "iptables"
_IP6TABLES = "ip6tables"
_NETWORK_APPLY_LOCK = threading.RLock()


def _run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    debug_os_sandbox_flow("linux.command", cmd=cmd)
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )


def _require_command(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(f"linux_network_enforcement_missing_command:{name}")
    return resolved


def _ensure_cgroup_root() -> None:
    if not _CGROUP_ROOT.exists() or not (_CGROUP_ROOT / "cgroup.controllers").exists():
        raise RuntimeError("linux_network_enforcement_requires_cgroup_v2")


def _read_process_cgroup_relative_path(pid: int) -> str:
    try:
        raw = Path(f"/proc/{int(pid)}/cgroup").read_text(encoding="utf-8")
    except Exception as exc:
        raise RuntimeError(f"linux_network_enforcement_cgroup_read_failed:{pid}") from exc
    for line in raw.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        if parts[0] == "0":
            relative = str(parts[2] or "").strip()
            if relative.startswith("/"):
                return relative.lstrip("/")
            return relative
    raise RuntimeError(f"linux_network_enforcement_cgroup_not_found:{pid}")


def _process_cgroup_base_path(pid: int) -> Path:
    relative = _read_process_cgroup_relative_path(pid)
    base = _CGROUP_ROOT / relative if relative else _CGROUP_ROOT
    if not base.exists() or not base.is_dir():
        raise RuntimeError(f"linux_network_enforcement_cgroup_base_missing:{base}")
    return base


def _cgroup_relative_path(pid: int) -> str:
    base_relative = _read_process_cgroup_relative_path(pid)
    suffix = f"{_CGROUP_PREFIX}_{int(pid)}"
    return f"{base_relative}/{suffix}".strip("/") if base_relative else suffix


def _cgroup_absolute_path(pid: int) -> Path:
    return _process_cgroup_base_path(pid) / f"{_CGROUP_PREFIX}_{int(pid)}"


def _chain_name(pid: int) -> str:
    return f"DEMOCRAI_OS_{int(pid)}"


def _current_pid(pid: int | None) -> int:
    return int(pid or os.getpid())


def _ensure_process_cgroup(pid: int) -> str:
    _ensure_cgroup_root()
    base_relative = _read_process_cgroup_relative_path(pid)
    current_suffix = f"{_CGROUP_PREFIX}_{int(pid)}"
    if base_relative == current_suffix or base_relative.endswith(f"/{current_suffix}"):
        return base_relative
    sandbox_root = _CGROUP_ROOT / base_relative if base_relative else _CGROUP_ROOT
    cgroup_relative = (
        f"{base_relative}/{current_suffix}".strip("/")
        if base_relative
        else current_suffix
    )
    cgroup_path = sandbox_root / current_suffix
    try:
        cgroup_path.mkdir(exist_ok=True)
    except PermissionError as exc:
        raise RuntimeError(
            f"linux_network_enforcement_requires_writable_cgroup_parent:{sandbox_root}"
        ) from exc
    try:
        (cgroup_path / "cgroup.procs").write_text(f"{pid}\n", encoding="utf-8")
    except PermissionError as exc:
        raise RuntimeError("linux_network_enforcement_requires_privileged_cgroup_write") from exc
    return cgroup_relative


def _resolve_endpoint_values(endpoint: NetworkEndpoint | dict[str, Any]) -> tuple[str, int, str]:
    if isinstance(endpoint, dict):
        host = str(endpoint.get("host") or "").strip()
        port = int(endpoint.get("port") or 0)
        protocol = str(endpoint.get("protocol") or "tcp").strip().lower()
        return host, port, protocol
    return (
        str(endpoint.host or "").strip(),
        int(endpoint.port or 0),
        str(endpoint.protocol or "tcp").strip().lower(),
    )


def _resolve_endpoint_addresses(
    endpoint: NetworkEndpoint | dict[str, Any],
) -> tuple[set[str], set[str]]:
    ipv4: set[str] = set()
    ipv6: set[str] = set()
    host, port, protocol = _resolve_endpoint_values(endpoint)
    if "*" in host:
        raise RuntimeError(
            f"linux_network_enforcement_unresolvable_wildcard_host:{host}:{port}"
        )
    socktype = socket.SOCK_DGRAM if protocol == "udp" else socket.SOCK_STREAM
    try:
        infos = socket.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socktype,
            proto=socket.IPPROTO_UDP if protocol == "udp" else socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise RuntimeError(
            f"linux_network_enforcement_dns_resolution_failed:{host}:{port}"
        ) from exc

    for family, _socktype, _proto, _canonname, sockaddr in infos:
        if family == socket.AF_INET:
            ipv4.add(str(sockaddr[0]))
        elif family == socket.AF_INET6:
            ipv6.add(str(sockaddr[0]))
    return ipv4, ipv6


def _run_iptables(cmd: list[str]) -> None:
    result = _run_command(cmd)
    if result.returncode != 0:
        stderr = str(result.stderr or "").strip()
        raise RuntimeError(f"linux_network_enforcement_command_failed:{' '.join(cmd)}:{stderr}")


def _best_effort_iptables(cmd: list[str]) -> None:
    result = _run_command(cmd)
    debug_os_sandbox_flow(
        "linux.command_result",
        cmd=cmd,
        returncode=result.returncode,
        stderr=str(result.stderr or "").strip(),
    )


def _delete_output_jump(iptables_cmd: str, cgroup_path: str, chain: str) -> None:
    _best_effort_iptables(
        [
            iptables_cmd,
            "-D",
            "OUTPUT",
            "-m",
            "cgroup",
            "--path",
            cgroup_path,
            "-j",
            chain,
        ]
    )


def _is_chain_already_exists_error(stderr: str) -> bool:
    return "chain already exists" in str(stderr or "").strip().lower()


def _create_chain(iptables_cmd: str, chain: str) -> None:
    _best_effort_iptables([iptables_cmd, "-F", chain])
    _best_effort_iptables([iptables_cmd, "-X", chain])
    create_cmd = [iptables_cmd, "-N", chain]
    result = _run_command(create_cmd)
    if result.returncode == 0:
        return
    stderr = str(result.stderr or "").strip()
    if not _is_chain_already_exists_error(stderr):
        raise RuntimeError(
            f"linux_network_enforcement_command_failed:{' '.join(create_cmd)}:{stderr}"
        )
    # A concurrent refresh, or a still-referenced chain, can leave the pending
    # chain in place after the best-effort delete above. Treat only that exact
    # condition as idempotent, and verify the chain is usable by flushing it.
    _run_iptables([iptables_cmd, "-F", chain])


def _append_rule(iptables_cmd: str, rule: list[str]) -> None:
    _run_iptables([iptables_cmd, "-A", *rule])


def _insert_rule(iptables_cmd: str, rule: list[str]) -> None:
    _run_iptables([iptables_cmd, "-I", *rule])


def _chain_names(pid: int) -> tuple[str, str]:
    base = _chain_name(pid)
    return f"{base}_A", f"{base}_B"


def _list_output_rules(iptables_cmd: str) -> list[str]:
    result = _run_command([iptables_cmd, "-S", "OUTPUT"])
    if result.returncode != 0:
        stderr = str(result.stderr or "").strip()
        raise RuntimeError(f"linux_network_enforcement_command_failed:{iptables_cmd} -S OUTPUT:{stderr}")
    return [str(line or "").strip() for line in str(result.stdout or "").splitlines()]


def _find_active_chain(
    iptables_cmd: str,
    *,
    cgroup_path: str,
    candidates: tuple[str, str],
) -> str | None:
    prefix = f"-A OUTPUT -m cgroup --path {cgroup_path} -j "
    for line in _list_output_rules(iptables_cmd):
        if not line.startswith(prefix):
            continue
        target = line[len(prefix):].strip()
        if target in candidates:
            return target
    return None


def _install_chain(
    *,
    iptables_cmd: str,
    pid: int,
    cgroup_path: str,
    loopback_destination: str,
    allowed_addresses: dict[str, dict[int, set[str]]],
) -> None:
    candidate_a, candidate_b = _chain_names(pid)
    active_chain = _find_active_chain(
        iptables_cmd,
        cgroup_path=cgroup_path,
        candidates=(candidate_a, candidate_b),
    )
    pending_chain = candidate_b if active_chain == candidate_a else candidate_a

    _delete_output_jump(iptables_cmd, cgroup_path, pending_chain)
    _create_chain(iptables_cmd, pending_chain)
    _append_rule(iptables_cmd, [pending_chain, "-o", "lo", "-j", "RETURN"])
    _append_rule(iptables_cmd, [pending_chain, "-d", loopback_destination, "-j", "RETURN"])
    for protocol, port_map in sorted(allowed_addresses.items()):
        for port, addresses in sorted(port_map.items()):
            for address in sorted(addresses):
                _append_rule(
                    iptables_cmd,
                    [
                        pending_chain,
                        "-p",
                        protocol,
                        "-d",
                        address,
                        "--dport",
                        str(int(port)),
                        "-j",
                        "RETURN",
                    ],
                )
    _append_rule(iptables_cmd, [pending_chain, "-j", "REJECT"])
    _insert_rule(
        iptables_cmd,
        ["OUTPUT", "1", "-m", "cgroup", "--path", cgroup_path, "-j", pending_chain],
    )
    for chain in (candidate_a, candidate_b):
        if chain == pending_chain:
            continue
        _delete_output_jump(iptables_cmd, cgroup_path, chain)
        _best_effort_iptables([iptables_cmd, "-F", chain])
        _best_effort_iptables([iptables_cmd, "-X", chain])


def _system_dns_endpoints() -> list[dict[str, Any]]:
    resolv_conf = Path("/etc/resolv.conf")
    if not resolv_conf.exists():
        return []
    endpoints: list[dict[str, Any]] = []
    try:
        raw = resolv_conf.read_text(encoding="utf-8")
    except Exception:
        return []
    for line in raw.splitlines():
        stripped = str(line or "").strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not stripped.startswith("nameserver "):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        host = str(parts[1] or "").strip()
        if not host:
            continue
        endpoints.extend(
            [
                {
                    "host": host,
                    "port": 53,
                    "protocol": "udp",
                    "source": "system.resolver",
                    "purpose": "dns",
                },
                {
                    "host": host,
                    "port": 53,
                    "protocol": "tcp",
                    "source": "system.resolver",
                    "purpose": "dns",
                },
            ]
        )
    return endpoints


def _build_address_maps_from_endpoints(
    endpoints: list[NetworkEndpoint | dict[str, Any]],
) -> tuple[dict[str, dict[int, set[str]]], dict[str, dict[int, set[str]]]]:
    ipv4_by_protocol: dict[str, dict[int, set[str]]] = {}
    ipv6_by_protocol: dict[str, dict[int, set[str]]] = {}
    for endpoint in list(endpoints or []):
        host, port, protocol = _resolve_endpoint_values(endpoint)
        if protocol not in {"tcp", "udp"}:
            continue
        if "*" in host:
            debug_os_sandbox_flow(
                "linux.skip_wildcard_endpoint",
                host=host,
                port=int(port),
                protocol=protocol,
            )
            continue
        ipv4, ipv6 = _resolve_endpoint_addresses(endpoint)
        if ipv4:
            ipv4_by_protocol.setdefault(protocol, {}).setdefault(int(port), set()).update(ipv4)
        if ipv6:
            ipv6_by_protocol.setdefault(protocol, {}).setdefault(int(port), set()).update(ipv6)
    return ipv4_by_protocol, ipv6_by_protocol


def _build_address_maps(
    allowlist: ApplicationNetworkAllowlist,
) -> tuple[dict[str, dict[int, set[str]]], dict[str, dict[int, set[str]]]]:
    return _build_address_maps_from_endpoints(
        [*list(allowlist.endpoints or []), *_system_dns_endpoints()]
    )


def _probe_cgroup_path_match(iptables_cmd: str, *, pid: int) -> None:
    cgroup_path = _read_process_cgroup_relative_path(pid)
    chain = f"DEMOCRAI_PROBE_{pid}"
    try:
        _run_iptables([iptables_cmd, "-N", chain])
        _run_iptables(
            [iptables_cmd, "-A", "OUTPUT", "-m", "cgroup", "--path", cgroup_path, "-j", chain]
        )
        _delete_output_jump(iptables_cmd, cgroup_path, chain)
    finally:
        _best_effort_iptables([iptables_cmd, "-F", chain])
        _best_effort_iptables([iptables_cmd, "-X", chain])


def is_linux_network_enforcement_supported() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    if not (_CGROUP_ROOT / "cgroup.controllers").exists():
        return False
    if shutil.which(_IPTABLES) is None:
        return False
    if shutil.which(_IP6TABLES) is None:
        return False
    return True


def ensure_linux_network_enforcement_ready() -> None:
    if not is_linux_network_enforcement_supported():
        raise RuntimeError("linux_network_enforcement_not_supported")

    iptables_cmd = _require_command(_IPTABLES)
    ip6tables_cmd = _require_command(_IP6TABLES)
    try:
        _probe_cgroup_path_match(iptables_cmd, pid=os.getpid())
    except RuntimeError as exc:
        raise RuntimeError("linux_network_enforcement_requires_net_admin") from exc
    try:
        _probe_cgroup_path_match(ip6tables_cmd, pid=os.getpid())
    except RuntimeError as exc:
        raise RuntimeError("linux_network_enforcement_requires_net_admin") from exc


def apply_application_network_allowlist(
    allowlist: ApplicationNetworkAllowlist,
    *,
    pid: int | None = None,
) -> None:
    resolved_pid = _current_pid(pid)
    debug_os_sandbox_flow(
        "linux.apply_requested",
        endpoint_count=len(allowlist.endpoints),
        pid=resolved_pid,
        supported=is_linux_network_enforcement_supported(),
    )
    if not is_linux_network_enforcement_supported():
        raise RuntimeError("linux_network_enforcement_not_supported")

    with _NETWORK_APPLY_LOCK:
        iptables_cmd = _require_command(_IPTABLES)
        ip6tables_cmd = _require_command(_IP6TABLES)
        cgroup_path = _ensure_process_cgroup(resolved_pid)
        chain = _chain_name(resolved_pid)
        ipv4_by_port, ipv6_by_port = _build_address_maps(allowlist)

        _install_chain(
            iptables_cmd=iptables_cmd,
            pid=resolved_pid,
            cgroup_path=cgroup_path,
            loopback_destination="127.0.0.0/8",
            allowed_addresses=ipv4_by_port,
        )
        _install_chain(
            iptables_cmd=ip6tables_cmd,
            pid=resolved_pid,
            cgroup_path=cgroup_path,
            loopback_destination="::1/128",
            allowed_addresses=ipv6_by_port,
        )
    debug_os_sandbox_flow(
        "linux.apply_completed",
        pid=resolved_pid,
        chain=chain,
        ipv4_ports=sorted({port for ports in ipv4_by_port.values() for port in ports}),
        ipv6_ports=sorted({port for ports in ipv6_by_port.values() for port in ports}),
    )


def apply_application_network_endpoints(
    endpoints: list[dict[str, Any]],
    *,
    pid: int | None = None,
) -> None:
    resolved_pid = _current_pid(pid)
    debug_os_sandbox_flow(
        "linux.apply_requested",
        endpoint_count=len(endpoints),
        pid=resolved_pid,
        supported=is_linux_network_enforcement_supported(),
    )
    if not is_linux_network_enforcement_supported():
        raise RuntimeError("linux_network_enforcement_not_supported")

    with _NETWORK_APPLY_LOCK:
        iptables_cmd = _require_command(_IPTABLES)
        ip6tables_cmd = _require_command(_IP6TABLES)
        cgroup_path = _ensure_process_cgroup(resolved_pid)
        chain = _chain_name(resolved_pid)
        ipv4_by_port, ipv6_by_port = _build_address_maps_from_endpoints(
            [*list(endpoints or []), *_system_dns_endpoints()]
        )

        _install_chain(
            iptables_cmd=iptables_cmd,
            pid=resolved_pid,
            cgroup_path=cgroup_path,
            loopback_destination="127.0.0.0/8",
            allowed_addresses=ipv4_by_port,
        )
        _install_chain(
            iptables_cmd=ip6tables_cmd,
            pid=resolved_pid,
            cgroup_path=cgroup_path,
            loopback_destination="::1/128",
            allowed_addresses=ipv6_by_port,
        )
    debug_os_sandbox_flow(
        "linux.apply_completed",
        pid=resolved_pid,
        chain=chain,
        ipv4_ports=sorted({port for ports in ipv4_by_port.values() for port in ports}),
        ipv6_ports=sorted({port for ports in ipv6_by_port.values() for port in ports}),
    )


def clear_application_network_allowlist(*, pid: int | None = None) -> None:
    resolved_pid = _current_pid(pid)
    debug_os_sandbox_flow(
        "linux.clear_requested",
        pid=resolved_pid,
        supported=is_linux_network_enforcement_supported(),
    )
    if not is_linux_network_enforcement_supported():
        raise RuntimeError("linux_network_enforcement_not_supported")

    chains = _chain_names(resolved_pid)
    cgroup_path = _read_process_cgroup_relative_path(resolved_pid)
    for command in (_require_command(_IPTABLES), _require_command(_IP6TABLES)):
        for chain in chains:
            _delete_output_jump(command, cgroup_path, chain)
            _best_effort_iptables([command, "-F", chain])
            _best_effort_iptables([command, "-X", chain])
    debug_os_sandbox_flow("linux.clear_completed", pid=resolved_pid, chain=_chain_name(resolved_pid))
