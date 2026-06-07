from __future__ import annotations

import os
import importlib
from typing import Any

from democrai.core.infrastructure.sandbox.os.base import (
    BaseFilesystemSandbox,
    BaseNetworkSandbox,
    BaseOsSandboxProvider,
    OsSandboxCapabilities,
    proxy_endpoint_payload,
)
from democrai.core.infrastructure.sandbox.os.launch_policy import (
    NETWORK_ALLOW_ALL,
    NETWORK_DENY,
    SandboxLaunchPolicy,
)
from democrai.core.runtime.foundation.app import app_ctx


class LinuxFilesystemSandbox(BaseFilesystemSandbox):
    def apply(self, policy: SandboxLaunchPolicy) -> None:
        from democrai.core.infrastructure.sandbox.os.linux.landlock import (
            apply_landlock_filesystem_rules,
            is_landlock_supported,
        )

        if not is_landlock_supported():
            if policy.audit_only:
                logger = getattr(app_ctx(), "logger", None)
                if logger is not None:
                    logger.warning(
                        "[Sandbox] Landlock is not supported on this system. Filesystem access rules will be ignored."
                    )
                return
            if policy.filesystem_access:
                raise RuntimeError("linux_sandbox_landlock_required")
            logger = getattr(app_ctx(), "logger", None)
            if logger is not None:
                logger.warning(
                    "[Sandbox] Landlock is not supported on this system. Filesystem access rules will be ignored."
                )
            return
        read_only_paths: list[str] = []
        read_write_paths: list[str] = []
        for item in policy.filesystem_access:
            if item.operation in {"create", "modify", "delete"}:
                read_write_paths.append(item.target)
            elif item.operation in {"read", "execute"}:
                read_only_paths.append(item.target)
        if read_only_paths or read_write_paths:
            apply_landlock_filesystem_rules(
                read_only_paths=read_only_paths,
                read_write_paths=read_write_paths,
            )


class LinuxNetworkSandbox(BaseNetworkSandbox):
    def apply(self, policy: SandboxLaunchPolicy, env: dict[str, str]) -> None:
        if policy.network_mode == NETWORK_ALLOW_ALL:
            return
        helper_mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.helper")

        if policy.network_mode == NETWORK_DENY:
            helper_mod.apply_application_network_endpoints_with_helper([], pid=os.getpid())
            return
        proxy_url = env.get("ALL_PROXY") or env.get("all_proxy") or ""
        helper_mod.apply_application_network_endpoints_with_helper(
            [proxy_endpoint_payload(proxy_url)],
            pid=os.getpid(),
        )


class LinuxOsSandboxProvider(BaseOsSandboxProvider):
    def __init__(self) -> None:
        super().__init__(
            filesystem=LinuxFilesystemSandbox(),
            network=LinuxNetworkSandbox(),
        )

    def capabilities(self) -> OsSandboxCapabilities:
        return OsSandboxCapabilities(
            filesystem=True,
            network_deny=True,
            network_proxy=True,
            network_allow_all=True,
            execute=True,
        )

    def apply_current_process_os_sandbox(self, config: Any) -> dict[str, object]:
        from democrai.core.infrastructure.sandbox.os.linux import process_restrictions

        details = process_restrictions.apply_process_restrictions(config)
        errors = [
            str(item.get("error"))
            for item in details.values()
            if isinstance(item, dict) and item.get("error")
        ]
        return {
            "provider": self.__class__.__name__,
            "applied": any(
                bool(item.get("applied"))
                for item in details.values()
                if isinstance(item, dict)
            ),
            "skipped": all(
                bool(item.get("skipped"))
                for item in details.values()
                if isinstance(item, dict)
            ),
            "error": "; ".join(errors) or None,
            "reason": None,
            "details": details,
        }

    def get_current_process_os_sandbox_status(self, config: Any) -> dict[str, object]:
        from democrai.core.infrastructure.sandbox.os.linux import process_restrictions

        return {
            "provider": self.__class__.__name__,
            "supported": True,
            "details": process_restrictions.get_process_restrictions_status(config),
        }
