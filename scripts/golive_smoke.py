#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from _golive_common import (
    DEFAULT_BASE_PORT,
    DEFAULT_HOST,
    close_logs,
    launch_instances,
    terminate_processes,
    wait_for_http_ping,
    ws_login_and_nav,
)


async def _run(args) -> int:
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
            print(f"[OK] /ping on {args.host}:{port}")

        result = await ws_login_and_nav(
            host=args.host,
            port=ports[0],
            username=args.username,
            password=args.password,
            path=args.path,
        )
        print(f"[OK] websocket init/login/nav on {args.host}:{ports[0]}")
        if args.show_jwt:
            print(result["jwt"])
        return 0
    finally:
        stuck = terminate_processes(procs)
        close_logs(log_handles)
        if stuck:
            print(f"[WARN] lingering processes after smoke: {stuck}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Democr.ai go-live smoke test")
    parser.add_argument("--exe", help="Executable to launch, otherwise runs dev main.py")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--base-port", type=int, default=DEFAULT_BASE_PORT)
    parser.add_argument("--instances", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="password")
    parser.add_argument("--path", default="/components/card")
    parser.add_argument("--dev", type=int, default=0)
    parser.add_argument("--log-dir", default="golive_logs/smoke")
    parser.add_argument("--show-jwt", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
