#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import time
from pathlib import Path

from _golive_common import (
    DEFAULT_BASE_PORT,
    DEFAULT_HOST,
    close_logs,
    launch_instances,
    terminate_processes,
    wait_for_http_ping,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Democr.ai shutdown/lifecycle check")
    parser.add_argument("--exe", help="Executable to launch, otherwise runs dev main.py")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--base-port", type=int, default=DEFAULT_BASE_PORT)
    parser.add_argument("--instances", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--shutdown-timeout", type=float, default=8.0)
    parser.add_argument("--dev", type=int, default=0)
    parser.add_argument("--log-dir", default="golive_logs/shutdown")
    args = parser.parse_args()

    log_dir = Path(args.log_dir).resolve()
    procs, ports, log_handles = launch_instances(
        instances=args.instances,
        workers=args.workers,
        exe_path=args.exe,
        host=args.host,
        base_port=args.base_port,
        log_dir=log_dir,
        dev=args.dev,
    )

    try:
        for port in ports:
            if not wait_for_http_ping(args.host, port, timeout_s=args.timeout):
                print(f"[FAIL] /ping not ready on {args.host}:{port}")
                return 1
            print(f"[OK] instance ready on {args.host}:{port}")

        started = time.perf_counter()
        stuck = terminate_processes(
            procs, sig=signal.SIGINT, timeout_s=args.shutdown_timeout
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if stuck:
            print(f"[FAIL] lingering processes after SIGINT: {stuck}")
            return 1

        print(f"[OK] clean shutdown in {elapsed_ms:.2f}ms")
        return 0
    finally:
        close_logs(log_handles)


if __name__ == "__main__":
    raise SystemExit(main())
