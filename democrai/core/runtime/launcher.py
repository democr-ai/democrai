from __future__ import annotations

import signal
import sys
import threading

from democrai.core.runtime.cli import build_parser, handle_cli_command, parse_args
from democrai.core.runtime.entrypoint import (
    core_runtime_options_from_args,
    start_core_runtime,
)
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.lifecycle.cleanup import run_shutdown_cleanup


_KNOWN_COMMANDS = {
    "migrate",
    "create-migration",
    "rollback",
    "migration-status",
    "validate-config",
    "setup",
    "install-engines",
    "install-extractors",
    "reset-install",
    "module-status",
    "knowledge-rebuild",
}


def _has_mode_arg(argv: list[str]) -> bool:
    for index, item in enumerate(argv):
        if item == "--mode":
            return index + 1 < len(argv)
        if item.startswith("--mode="):
            return True
    return False


def _with_packaged_defaults(argv: list[str]) -> list[str]:
    if _has_mode_arg(argv):
        return argv
    return ["--mode", "server", *argv]


def _run_helper_process(argv: list[str]) -> int:
    from democrai.core.infrastructure.sandbox.os import helper_entrypoint

    filtered = [item for item in argv if item != "--os-sandbox-helper-process"]
    original_argv = sys.argv
    try:
        sys.argv = [original_argv[0], *filtered]
        result = helper_entrypoint.main()
        if result is None:
            return 0
        return int(result)
    finally:
        sys.argv = original_argv


def _wait_for_shutdown() -> int:
    ctx = app_ctx()
    stop_event = threading.Event()
    exit_code = {"value": 0}
    signal_state = {"count": 0}

    def _request_shutdown(_signum, _frame) -> None:
        signal_state["count"] += 1
        if signal_state["count"] == 1:
            exit_code["value"] = 130
            stop_event.set()
            return
        raise SystemExit(130)

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_shutdown)

    try:
        stop_event.wait()
    finally:
        run_shutdown_cleanup(ctx, reloader=None, child_proc=None)
    return int(exit_code["value"])


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if "--os-sandbox-helper-process" in raw_argv:
        return _run_helper_process(raw_argv)
    if any(item in {"-h", "--help"} for item in raw_argv):
        try:
            build_parser().parse_args(raw_argv)
        except SystemExit as exc:
            if exc.code is None:
                return 0
            return int(exc.code)
        return 0

    args = parse_args(_with_packaged_defaults(raw_argv))
    cli_rc = handle_cli_command(args)
    if cli_rc is not None:
        return int(cli_rc)

    client_value = getattr(args, "client", "")
    client_name = (
        client_value.strip()
        if isinstance(client_value, str)
        else str(client_value).strip()
    )
    if client_name:
        print(
            "[democrai] The installed package launcher does not start clients. "
            "Use the repository runner main.py for clients or run the client separately.",
            file=sys.stderr,
        )
        return 2

    mode_value = getattr(args, "mode", "")
    mode_name = (
        mode_value.strip() if isinstance(mode_value, str) else str(mode_value).strip()
    )
    if mode_name != "server":
        print(
            "[democrai] The installed package launcher starts the core server only. "
            "Use --mode server, or use the repository runner main.py for desktop mode.",
            file=sys.stderr,
        )
        return 2

    worker_count = getattr(args, "workers", 1)
    if worker_count is None:
        worker_count = 1
    if int(worker_count) != 1:
        print(
            "[democrai] The installed package launcher currently supports one worker. "
            "Use the repository runner main.py for multi-worker development.",
            file=sys.stderr,
        )
        return 2

    start_core_runtime(core_runtime_options_from_args(args))
    return _wait_for_shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
