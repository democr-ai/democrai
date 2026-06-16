from __future__ import annotations

from democrai.core.infrastructure.sandbox.os.launch_policy import SandboxLaunchPolicy
from democrai.core.infrastructure.sandbox.os.windows.provider import WindowsOsSandboxProvider


class WindowsCoreLaunchStrategy:
    requires_relaunch = True
    uses_spawn_broker = True

    def run(self, policy: SandboxLaunchPolicy) -> None:
        WindowsOsSandboxProvider().run(policy)

    def spawn(
        self,
        policy: SandboxLaunchPolicy,
        *,
        pass_fds: tuple[int, ...] = (),
        stdin=None,
        stdout=None,
        stderr=None,
    ):
        return WindowsOsSandboxProvider().spawn(
            policy,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )
