from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


def _ensure_application_root_on_path() -> None:
    if getattr(sys, "frozen", False):
        return
    app_root = Path(__file__).resolve().parents[5]
    if not (app_root / "democrai").is_dir():
        return
    app_root_str = str(app_root)
    if app_root_str not in sys.path:
        sys.path.insert(0, app_root_str)


_ensure_application_root_on_path()

from democrai.core.platform.config.yaml_config import YamlConfigProvider
from democrai.core.runtime.foundation.paths import get_data_dir


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--os-sandbox-helper-socket", default="")
    parser.add_argument("--os-sandbox-helper-policy-file", default="")
    parser.add_argument("--os-sandbox-helper-refresh-seconds", type=int, default=60)
    parser.add_argument("--os-sandbox-helper-parent-pid", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    from democrai.core.infrastructure.sandbox.os.helper import (
        get_os_sandbox_helper_socket_path,
        get_os_sandbox_policy_file_path,
    )
    from democrai.core.infrastructure.sandbox.os.helper_process import (
        run_os_sandbox_helper_server,
    )

    args = _parse_args()
    config = None
    config_path = os.path.join(get_data_dir(), "config.yaml")
    if os.path.exists(config_path):
        config = YamlConfigProvider(config_path)

    if config is not None and not bool(config.get("sandbox.os.enabled", False)):
        raise RuntimeError("os_sandbox_helper_disabled_in_config")

    socket_path = str(args.os_sandbox_helper_socket or "").strip()
    if not socket_path:
        socket_path = get_os_sandbox_helper_socket_path(config)

    policy_file = str(args.os_sandbox_helper_policy_file or "").strip()
    if not policy_file:
        policy_file = get_os_sandbox_policy_file_path(config)

    return int(
        asyncio.run(
            run_os_sandbox_helper_server(
                socket_path,
                policy_file=policy_file,
                refresh_seconds=int(args.os_sandbox_helper_refresh_seconds or 60),
                parent_pid=args.os_sandbox_helper_parent_pid,
            )
        )
        or 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
