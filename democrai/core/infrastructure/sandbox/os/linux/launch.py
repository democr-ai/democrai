from __future__ import annotations

import subprocess

from democrai.core.infrastructure.sandbox.os.launch_policy import SandboxLaunchPolicy


class LinuxCoreLaunchStrategy:
    requires_relaunch = False
    uses_spawn_broker = False

    def run(self, policy: SandboxLaunchPolicy) -> None:
        raise RuntimeError("os_sandbox_core_relaunch_not_required:linux")

    def spawn(
        self,
        policy: SandboxLaunchPolicy,
        *,
        pass_fds: tuple[int, ...] = (),
        stdin=None,
        stdout=None,
        stderr=None,
    ):
        return subprocess.Popen(
            policy.command,
            cwd=policy.cwd,
            env=policy.env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            pass_fds=pass_fds,
            close_fds=True,
        )
