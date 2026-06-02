from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class RuntimeHandle:
    args: Any
    endpoint: str | None = None
    exit_code: int | None = None


def _set_runtime_path_env_if_missing(
    *,
    app_dir: str,
    env_name: str,
    dirname: str,
) -> None:
    if os.environ.get(env_name):
        return
    candidate = os.path.join(app_dir, dirname)
    if os.path.isdir(candidate):
        os.environ[env_name] = os.path.realpath(os.path.abspath(candidate))


def _configure_runtime_path_environment(app_dir: str) -> None:
    from democrai.core.runtime.entrypoint import (
        ENGINES_PATH_ENV,
        EXTRACTORS_PATH_ENV,
        MODULES_PATH_ENV,
    )

    _set_runtime_path_env_if_missing(
        app_dir=app_dir,
        env_name=MODULES_PATH_ENV,
        dirname="modules",
    )
    _set_runtime_path_env_if_missing(
        app_dir=app_dir,
        env_name=ENGINES_PATH_ENV,
        dirname="engines",
    )
    _set_runtime_path_env_if_missing(
        app_dir=app_dir,
        env_name=EXTRACTORS_PATH_ENV,
        dirname="extractors",
    )


def start(
    *,
    argv: list[str] | None = None,
    app_dir: str | None = None,
    configure_args=None,
) -> RuntimeHandle:
    from democrai.core.platform.utils.env import build_desktop_ipc_server_name
    from democrai.core.runtime.cli import handle_cli_command, parse_args
    from democrai.core.runtime.entrypoint import (
        core_runtime_options_from_args,
        start_core_runtime,
    )
    from democrai.core.runtime.launcher import _run_helper_process

    if app_dir:
        _configure_runtime_path_environment(app_dir)

    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(raw_argv)
    if getattr(args, "os_sandbox_helper_process", False):
        return RuntimeHandle(
            args=args,
            exit_code=int(_run_helper_process(raw_argv) or 0),
        )

    cli_rc = handle_cli_command(args)
    if cli_rc is not None:
        return RuntimeHandle(args=args, exit_code=int(cli_rc))

    if callable(configure_args):
        configure_args(args)

    if (
        str(getattr(args, "mode", "") or "") == "server"
        and int(getattr(args, "workers", 1) or 1) > 1
        and not bool(getattr(args, "server_worker", False))
    ):
        return RuntimeHandle(args=args)

    if str(getattr(args, "mode", "") or "") == "desktop":
        os.environ.setdefault(
            "DEMOCRAI_IPC_SERVER_NAME",
            build_desktop_ipc_server_name(getattr(args, "port", 8000)),
        )

    endpoint = start_core_runtime(core_runtime_options_from_args(args))
    return RuntimeHandle(args=args, endpoint=endpoint)


def stop(*, reloader: Any | None = None, child_proc: Any | None = None) -> None:
    from democrai.core.runtime.foundation.app import app_ctx
    from democrai.core.runtime.lifecycle.cleanup import run_shutdown_cleanup

    run_shutdown_cleanup(app_ctx(), reloader=reloader, child_proc=child_proc)
