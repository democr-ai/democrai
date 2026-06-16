from __future__ import annotations

from democrai.core.infrastructure.sandbox.os.base import (
    BaseOsSandboxProvider,
    OsSandboxCapabilities,
    network_env,
)
from democrai.core.infrastructure.sandbox.os.launch_policy import (
    SandboxLaunchPolicy,
)
from democrai.core.infrastructure.sandbox.os.windows.low_integrity import (
    WindowsPreparedSandbox,
    cleanup_windows_low_integrity,
    launch_low_integrity_process,
    prepare_windows_low_integrity,
    spawn_low_integrity_process,
)
from democrai.core.infrastructure.sandbox.os.windows.winapi import is_windows


class WindowsOsSandboxProvider(BaseOsSandboxProvider):
    def __init__(self) -> None:
        super().__init__()
        self._prepared_sandbox: WindowsPreparedSandbox | None = None

    def capabilities(self) -> OsSandboxCapabilities:
        return OsSandboxCapabilities(
            filesystem=True,
            network_deny=True,
            network_proxy=True,
            network_allow_all=True,
            execute=True,
        )

    def supports(self, policy: SandboxLaunchPolicy) -> bool:
        return bool(policy.command)

    def prepare(self, policy: SandboxLaunchPolicy) -> SandboxLaunchPolicy:
        if not self.supports(policy):
            raise RuntimeError("windows_sandbox_policy_not_supported")
        if not is_windows():
            raise RuntimeError("windows_sandbox_low_integrity_unavailable")
        return policy

    def prepare_launch_env(
        self,
        policy: SandboxLaunchPolicy,
        env: dict[str, str],
    ) -> str:
        # No special shared-memory SID is needed under Low integrity: the
        # sandboxed core runs as the same user, and the IPC shared-memory
        # protocol is creator-writes (the core writes only its own Low objects
        # and reads the parent's Medium objects via read-up). Returning "" makes
        # the shm DACL grant in local_binary_payload a no-op.
        return ""

    def apply_current_process(
        self,
        policy: SandboxLaunchPolicy,
        env: dict[str, str],
    ) -> None:
        return

    def exec(self, policy: SandboxLaunchPolicy, env: dict[str, str]) -> None:
        if self._prepared_sandbox is None:
            raise RuntimeError("windows_sandbox_low_integrity_unavailable:not_prepared")
        try:
            exit_code = int(launch_low_integrity_process(policy, self._prepared_sandbox, env))
        finally:
            cleanup_windows_low_integrity(self._prepared_sandbox)
        raise SystemExit(exit_code)

    def run(self, policy: SandboxLaunchPolicy) -> None:
        prepared = self.prepare(policy)
        env = network_env(prepared)
        self._prepared_sandbox = prepare_windows_low_integrity(
            prepared,
            proxy_url=str(env.get("ALL_PROXY") or env.get("all_proxy") or "").strip(),
        )
        self.apply_current_process(prepared, env)
        self.exec(prepared, env)

    def spawn(self, policy: SandboxLaunchPolicy, *, stdin=None, stdout=None, stderr=None):
        prepared = self.prepare(policy)
        env = network_env(prepared)
        sandbox = prepare_windows_low_integrity(
            prepared,
            proxy_url=str(env.get("ALL_PROXY") or env.get("all_proxy") or "").strip(),
        )
        self.apply_current_process(prepared, env)
        return spawn_low_integrity_process(
            prepared,
            sandbox,
            env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )
