import argparse
import asyncio
import resource

from scripts.multi_core_benchmark_profiles import PROFILE_PRESETS
from scripts.multi_core_benchmark_runtime import main


def _raise_fd_limit() -> None:
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        print(f"Current FD limits: soft={soft}, hard={hard}")
        resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
        print(f"Updated FD limits: soft={hard}, hard={hard}")
    except Exception as exc:
        print(f"Failed to update FD limits: {exc}")


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workers", type=int, default=None, help="Workers per instance"
    )
    parser.add_argument(
        "--instances", type=int, default=1, help="Server instances to launch"
    )
    parser.add_argument("--clients", type=int, default=None, help="Clients per worker")
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="Legacy fixed-cycle mode. If omitted, the benchmark runs by duration.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=None,
        help="Run nav load for a fixed duration after login.",
    )
    parser.add_argument(
        "--exe", type=str, default=None, help="Path to compiled executable"
    )
    parser.add_argument(
        "--profile-log-summary",
        action="store_true",
        help="Parse and print RequestProfile summary from server_worker_0.log",
    )
    parser.add_argument(
        "--profile",
        choices=("stress", "interactive", "custom"),
        default="stress",
        help="Benchmark profile preset",
    )
    parser.add_argument(
        "--path",
        dest="paths",
        action="append",
        default=None,
        help="Optional nav path override (repeatable).",
    )
    parser.add_argument(
        "--think-time-ms",
        type=int,
        default=None,
        help="Optional client think time between nav requests.",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=30.0,
        help="Maximum wait for login/nav websocket responses in fixed-cycle mode.",
    )
    return parser.parse_args()


def run() -> None:
    _raise_fd_limit()
    args = _parse_args()

    selected = PROFILE_PRESETS.get(args.profile)
    workers = (
        args.workers
        if args.workers is not None
        else (selected.workers if selected else 16)
    )
    clients = (
        args.clients
        if args.clients is not None
        else (selected.clients if selected else 10)
    )
    cycles = (
        args.cycles
        if args.cycles is not None
        else (selected.cycles if selected else 30)
    )
    duration_seconds = (
        args.duration_seconds
        if args.duration_seconds is not None
        else (None if args.cycles is not None else (selected.duration_seconds if selected else 30))
    )

    asyncio.run(
        main(
            workers_per_instance=workers,
            num_instances=args.instances,
            clients_per_worker=clients,
            cycles=cycles,
            duration_seconds=duration_seconds,
            exe_path=args.exe,
            profile_log_summary=args.profile_log_summary,
            profile_name=args.profile,
            nav_paths_override=args.paths,
            think_time_ms_override=args.think_time_ms,
            request_timeout_seconds=args.request_timeout_seconds,
        )
    )


if __name__ == "__main__":
    run()
