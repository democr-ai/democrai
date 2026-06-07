from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from democrai.core.infrastructure.sandbox.os.launch_policy import (
    NETWORK_ALLOW_ALL,
    NETWORK_DENY,
    NETWORK_PROXY,
    NetworkLaunchEndpoint,
    SandboxLaunchPolicy,
)


@dataclass(frozen=True)
class OsSandboxCapabilities:
    filesystem: bool
    network_deny: bool
    network_proxy: bool
    network_allow_all: bool
    execute: bool


class BaseFilesystemSandbox:
    def apply(self, policy: SandboxLaunchPolicy) -> None:
        if policy.filesystem_access:
            raise RuntimeError("os_sandbox_filesystem_not_supported")


class BaseNetworkSandbox:
    def apply(self, policy: SandboxLaunchPolicy, env: dict[str, str]) -> None:
        if policy.network_mode != NETWORK_ALLOW_ALL:
            raise RuntimeError(f"os_sandbox_network_not_supported:{policy.network_mode}")


class BaseOsSandboxProvider:
    filesystem: BaseFilesystemSandbox
    network: BaseNetworkSandbox

    def __init__(
        self,
        *,
        filesystem: BaseFilesystemSandbox | None = None,
        network: BaseNetworkSandbox | None = None,
    ) -> None:
        self.filesystem = filesystem or BaseFilesystemSandbox()
        self.network = network or BaseNetworkSandbox()

    def capabilities(self) -> OsSandboxCapabilities:
        return OsSandboxCapabilities(
            filesystem=type(self.filesystem) is not BaseFilesystemSandbox,
            network_deny=type(self.network) is not BaseNetworkSandbox,
            network_proxy=type(self.network) is not BaseNetworkSandbox,
            network_allow_all=True,
            execute=True,
        )

    def supports(self, policy: SandboxLaunchPolicy) -> bool:
        if not policy.command:
            return False
        capabilities = self.capabilities()
        if policy.filesystem_access and not capabilities.filesystem:
            return False
        if policy.network_mode == NETWORK_DENY and not capabilities.network_deny:
            return False
        if policy.network_mode == NETWORK_PROXY and not capabilities.network_proxy:
            return False
        if policy.network_mode == NETWORK_ALLOW_ALL and not capabilities.network_allow_all:
            return False
        return bool(capabilities.execute)

    def prepare(self, policy: SandboxLaunchPolicy) -> SandboxLaunchPolicy:
        if not self.supports(policy):
            raise RuntimeError("os_sandbox_policy_not_supported")
        return policy

    def apply_current_process_os_sandbox(self, config) -> dict[str, object]:
        raise RuntimeError("os_sandbox_current_process_not_supported")

    def get_current_process_os_sandbox_status(self, config) -> dict[str, object]:
        return {
            "provider": self.__class__.__name__,
            "supported": False,
            "details": {},
        }

    def env(self, policy: SandboxLaunchPolicy) -> dict[str, str]:
        return network_env(policy)

    def apply_current_process(
        self,
        policy: SandboxLaunchPolicy,
        env: dict[str, str],
    ) -> None:
        self.filesystem.apply(policy)
        self.network.apply(policy, env)

    def exec(self, policy: SandboxLaunchPolicy, env: dict[str, str]) -> None:
        if policy.cwd is not None:
            os.chdir(str(policy.cwd))
        os.execvpe(policy.command[0], policy.command, env)

    def run(self, policy: SandboxLaunchPolicy) -> None:
        prepared = self.prepare(policy)
        env = self.env(prepared)
        self.apply_current_process(prepared, env)
        self.exec(prepared, env)


class NoopOsSandboxProvider(BaseOsSandboxProvider):
    def capabilities(self) -> OsSandboxCapabilities:
        return OsSandboxCapabilities(
            filesystem=False,
            network_deny=False,
            network_proxy=False,
            network_allow_all=False,
            execute=False,
        )

    def prepare(self, policy: SandboxLaunchPolicy) -> SandboxLaunchPolicy:
        if not policy.audit_only:
            raise RuntimeError("os_sandbox_provider_unavailable")
        return policy

    def apply_current_process_os_sandbox(self, config) -> dict[str, object]:
        raise RuntimeError("os_sandbox_provider_unavailable")

    def apply_current_process(
        self,
        policy: SandboxLaunchPolicy,
        env: dict[str, str],
    ) -> None:
        return


def network_env(policy: SandboxLaunchPolicy) -> dict[str, str]:
    env = dict(os.environ if policy.env is None else policy.env)
    if policy.network_mode == NETWORK_DENY:
        return env
    if policy.network_mode == NETWORK_ALLOW_ALL:
        return env
    proxy_url = _loopback_proxy_url(str(env.get("ALL_PROXY") or env.get("all_proxy") or "").strip())
    if not proxy_url:
        proxy_url = _loopback_proxy_url(proxy_url_for_policy(policy))
    if not proxy_url:
        raise RuntimeError("os_sandbox_proxy_required")
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env[key] = proxy_url
    env["NO_PROXY"] = "127.0.0.1,localhost,::1"
    env["no_proxy"] = "127.0.0.1,localhost,::1"
    return env


def proxy_url_for_policy(policy: SandboxLaunchPolicy) -> str:
    if policy.network_mode != NETWORK_PROXY:
        return ""
    from democrai.core.infrastructure.sandbox.os.helper import (
        start_application_network_proxy_session_with_helper,
    )
    from democrai.core.infrastructure.sandbox.os.models import (
        ApplicationNetworkAllowlist,
    )

    endpoints = [
        _network_endpoint_from_target(item)
        for item in policy.network_endpoints
    ]
    endpoints = [item for item in endpoints if item is not None]
    if not endpoints:
        raise RuntimeError("os_sandbox_proxy_endpoints_required")
    session = start_application_network_proxy_session_with_helper(
        ApplicationNetworkAllowlist(endpoints=endpoints)
    )
    proxy_url = str(session.get("proxy_url") or "").strip()
    if not proxy_url:
        raise RuntimeError("os_sandbox_proxy_url_missing")
    return proxy_url


def proxy_endpoint_payload(proxy_url: str) -> dict[str, str | int]:
    parsed = urlparse(proxy_url)
    host = parsed.hostname or ""
    port = int(parsed.port or 0)
    if not _loopback_proxy_url(proxy_url) or not host or port <= 0:
        raise RuntimeError("os_sandbox_proxy_endpoint_invalid")
    return {
        "host": host,
        "port": port,
        "protocol": "tcp",
        "source": "sandbox_proxy",
        "purpose": "sandbox_network_proxy",
    }


def _loopback_proxy_url(proxy_url: str) -> str:
    value = str(proxy_url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    host = str(parsed.hostname or "").strip().lower()
    port = int(parsed.port or 0)
    if host == "localhost":
        host = "127.0.0.1"
    if host not in {"127.0.0.1", "::1"} or port <= 0:
        return ""
    return value


def _network_endpoint_from_target(item: NetworkLaunchEndpoint):
    from democrai.core.infrastructure.sandbox.os.normalize import endpoint_from_target

    return endpoint_from_target(
        item.target,
        source="sandbox_launch_policy",
        purpose=f"network_{item.operation}",
    )
