#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = APP_DIR.parent
SCRIPT_DIR = Path(__file__).resolve().parent
BENCHMARK_SCRIPT = PROJECT_DIR / "scripts" / "multi_core_benchmark.py"


def _run_step(name: str, cmd: list[str]) -> int:
    print(f"\n=== {name} ===")
    print(" ".join(cmd))
    return subprocess.run(cmd, cwd=str(APP_DIR)).returncode


def _python_cmd(script: Path) -> list[str]:
    return [sys.executable, str(script)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Democr.ai go-live test suite")
    parser.add_argument("--exe", help="Executable to launch, otherwise runs dev main.py")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--base-port", type=int, default=8001)
    parser.add_argument("--instances", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--clients", type=int, default=20)
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--duration-seconds", type=int)
    parser.add_argument("--dev", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--skip-shutdown", action="store_true")
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--profile-log-summary", action="store_true")
    args = parser.parse_args()

    start = time.perf_counter()

    if not args.skip_smoke:
        smoke_cmd = _python_cmd(SCRIPT_DIR / "golive_smoke.py")
        smoke_cmd.extend(
            [
                "--host",
                args.host,
                "--base-port",
                str(args.base_port),
                "--instances",
                str(args.instances),
                "--workers",
                str(args.workers),
                "--timeout",
                str(args.timeout),
                "--dev",
                str(args.dev),
            ]
        )
        if args.exe:
            smoke_cmd.extend(["--exe", args.exe])
        rc = _run_step("Smoke", smoke_cmd)
        if rc != 0:
            return rc

    if not args.skip_shutdown:
        shutdown_cmd = _python_cmd(SCRIPT_DIR / "golive_shutdown_check.py")
        shutdown_cmd.extend(
            [
                "--host",
                args.host,
                "--base-port",
                str(args.base_port),
                "--instances",
                str(args.instances),
                "--workers",
                str(args.workers),
                "--timeout",
                str(args.timeout),
                "--dev",
                str(args.dev),
            ]
        )
        if args.exe:
            shutdown_cmd.extend(["--exe", args.exe])
        rc = _run_step("Shutdown", shutdown_cmd)
        if rc != 0:
            return rc

    if not args.skip_benchmark:
        benchmark_cmd = [
            sys.executable,
            str(BENCHMARK_SCRIPT),
            "--workers",
            str(args.workers),
            "--instances",
            str(args.instances),
            "--clients",
            str(args.clients),
            "--cycles",
            str(args.cycles),
        ]
        if args.duration_seconds:
            benchmark_cmd.extend(["--duration-seconds", str(args.duration_seconds)])
        if args.exe:
            benchmark_cmd.extend(["--exe", args.exe])
        if args.profile_log_summary:
            benchmark_cmd.append("--profile-log-summary")
        rc = _run_step("Benchmark", benchmark_cmd)
        if rc != 0:
            return rc

    total_s = time.perf_counter() - start
    print(f"\n[OK] go-live suite completed in {total_s:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
