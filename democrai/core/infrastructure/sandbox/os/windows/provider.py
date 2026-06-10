from __future__ import annotations

from democrai.core.infrastructure.sandbox.os.base import (
    BaseOsSandboxProvider,
    OsSandboxCapabilities,
    network_env,
)
from democrai.core.infrastructure.sandbox.os.launch_policy import (
    SandboxLaunchPolicy,
)
from democrai.core.infrastructure.sandbox.os.windows.appcontainer import (
    WindowsPreparedSandbox,
    cleanup_windows_appcontainer,
    is_windows,
    launch_appcontainer_process,
    spawn_appcontainer_process,
    prepare_windows_appcontainer,
)


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
            raise RuntimeError("windows_sandbox_appcontainer_unavailable")
        return policy

    def prepare_launch_env(
        self,
        policy: SandboxLaunchPolicy,
        env: dict[str, str],
    ) -> str:
        from democrai.core.infrastructure.sandbox.os.windows.appcontainer import (
            shared_memory_package_sid,
        )

        package_sid = shared_memory_package_sid(policy)
        if package_sid:
            env["DEMOCRAI_OS_SANDBOX_APPCONTAINER_SID"] = package_sid
        return package_sid

    def apply_current_process(
        self,
        policy: SandboxLaunchPolicy,
        env: dict[str, str],
    ) -> None:
        return

    def exec(self, policy: SandboxLaunchPolicy, env: dict[str, str]) -> None:
        if self._prepared_sandbox is None:
            raise RuntimeError("windows_sandbox_appcontainer_unavailable:not_prepared")
        try:
            exit_code = int(launch_appcontainer_process(policy, self._prepared_sandbox, env))
        finally:
            cleanup_windows_appcontainer(self._prepared_sandbox)
        raise SystemExit(exit_code)

    def run(self, policy: SandboxLaunchPolicy) -> None:
        prepared = self.prepare(policy)
        env = network_env(prepared)
        self._prepared_sandbox = prepare_windows_appcontainer(
            prepared,
            proxy_url=str(env.get("ALL_PROXY") or env.get("all_proxy") or "").strip(),
        )
        self.apply_current_process(prepared, env)
        self.exec(prepared, env)

    def spawn(self, policy: SandboxLaunchPolicy):
        prepared = self.prepare(policy)
        env = network_env(prepared)
        sandbox = prepare_windows_appcontainer(
            prepared,
            proxy_url=str(env.get("ALL_PROXY") or env.get("all_proxy") or "").strip(),
        )
        self.apply_current_process(prepared, env)
        return spawn_appcontainer_process(prepared, sandbox, env)
