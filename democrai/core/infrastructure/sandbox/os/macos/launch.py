from __future__ import annotations

import os
import shutil
import subprocess

from democrai.core.infrastructure.sandbox.os.launch_policy import SandboxLaunchPolicy
from democrai.core.infrastructure.sandbox.os.macos.provider import (
    MacOSOsSandboxProvider,
    seatbelt_profile,
    write_seatbelt_profile,
)


class MacOSCoreLaunchStrategy:
    requires_relaunch = True
    uses_spawn_broker = True

    def run(self, policy: SandboxLaunchPolicy) -> None:
        MacOSOsSandboxProvider().run(policy)

    def spawn(
        self,
        policy: SandboxLaunchPolicy,
        *,
        pass_fds: tuple[int, ...] = (),
        stdin=None,
        stdout=None,
        stderr=None,
    ):
        provider = MacOSOsSandboxProvider()
        prepared = provider.prepare(policy)
        env = provider.env(prepared)
        executable = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        profile = seatbelt_profile(
            prepared,
            proxy_url=str(env.get("ALL_PROXY") or env.get("all_proxy") or "").strip(),
        )
        profile_path = write_seatbelt_profile(profile)
        return subprocess.Popen(
            [executable, "-f", str(profile_path), "--", *prepared.command],
            cwd=os.getcwd() if prepared.cwd is None else str(prepared.cwd),
            env=env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            pass_fds=pass_fds,
            close_fds=True,
        )
