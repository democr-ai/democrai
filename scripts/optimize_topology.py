#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = APP_DIR.parent
BENCHMARK_SCRIPT = PROJECT_DIR / "scripts" / "multi_core_benchmark.py"

THROUGHPUT_RE = re.compile(r"Throughput:\s+([0-9.]+)\s+req/s")
AVG_LAT_RE = re.compile(r"Avg Latency:\s+([0-9.]+)ms")
P95_RE = re.compile(r"95th Percentile:\s+([0-9.]+)ms")
ERRORS_RE = re.compile(r"Errors:\s+([0-9]+)")
DURATION_RE = re.compile(r"Total Duration:\s+([0-9.]+)s")
REQUESTS_RE = re.compile(r"Total Requests:\s+([0-9]+)")


@dataclass
class BenchResult:
    instances: int
    workers: int
    throughput: float
    avg_latency_ms: float
    p95_ms: float
    errors: int
    duration_s: float
    total_requests: int
    stdout: str

    @property
    def score(self) -> float:
        if self.errors > 0:
            return -1.0
        return self.throughput


def _parse_metric(pattern: re.Pattern[str], text: str, name: str, cast=float):
    match = pattern.search(text)
    if not match:
        raise RuntimeError(f"Unable to parse '{name}' from benchmark output")
    return cast(match.group(1))


def run_benchmark(
    *,
    exe: str | None,
    instances: int,
    workers: int,
    clients: int,
    cycles: int,
    duration_seconds: int | None,
    extra_env: dict[str, str],
) -> BenchResult:
    cmd = [
        sys.executable,
        str(BENCHMARK_SCRIPT),
        "--instances",
        str(instances),
        "--workers",
        str(workers),
        "--clients",
        str(clients),
        "--cycles",
        str(cycles),
    ]
    if duration_seconds:
        cmd.extend(["--duration-seconds", str(duration_seconds)])
    if exe:
        cmd.extend(["--exe", exe])

    env = dict(extra_env)
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(APP_DIR),
        capture_output=True,
        text=True,
        env=env,
    )
    elapsed = time.perf_counter() - started
    output = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")

    if proc.returncode != 0:
        raise RuntimeError(
            f"Benchmark failed for instances={instances}, workers={workers}\n{output}"
        )

    return BenchResult(
        instances=instances,
        workers=workers,
        throughput=_parse_metric(THROUGHPUT_RE, output, "throughput"),
        avg_latency_ms=_parse_metric(AVG_LAT_RE, output, "avg latency"),
        p95_ms=_parse_metric(P95_RE, output, "p95"),
        errors=_parse_metric(ERRORS_RE, output, "errors", int),
        duration_s=_parse_metric(DURATION_RE, output, "duration"),
        total_requests=_parse_metric(REQUESTS_RE, output, "requests", int),
        stdout=output,
    )


def improves(
    baseline: BenchResult,
    candidate: BenchResult,
    *,
    min_improvement_ratio: float,
    max_p95_ms: float | None,
) -> bool:
    if candidate.errors > 0:
        return False
    if max_p95_ms is not None and candidate.p95_ms > max_p95_ms:
        return False
    required = baseline.throughput * (1.0 + min_improvement_ratio)
    return candidate.throughput > required


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search for the best instances/workers topology using the existing benchmark."
    )
    parser.add_argument("--exe", help="Path or command name of the compiled executable")
    parser.add_argument("--clients", type=int, default=50, help="Clients per worker")
    parser.add_argument("--cycles", type=int, default=30, help="Nav cycles per client")
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=None,
        help="Run each benchmark for a fixed duration instead of fixed cycles",
    )
    parser.add_argument("--max-instances", type=int, default=8)
    parser.add_argument("--max-workers", type=int, default=16)
    parser.add_argument(
        "--min-improvement-ratio",
        type=float,
        default=0.03,
        help="Minimum throughput improvement ratio required to keep scaling",
    )
    parser.add_argument(
        "--max-p95-ms",
        type=float,
        default=None,
        help="Reject configurations whose p95 exceeds this value",
    )
    parser.add_argument(
        "--results-json",
        default="topology_search_results.json",
        help="Where to write all measured results",
    )
    args = parser.parse_args()

    extra_env = dict(os.environ)

    results: list[BenchResult] = []

    def benchmark(instances: int, workers: int) -> BenchResult:
        print(f"\n[Search] Benchmarking instances={instances}, workers={workers}")
        result = run_benchmark(
            exe=args.exe,
            instances=instances,
            workers=workers,
            clients=args.clients,
            cycles=args.cycles,
            duration_seconds=args.duration_seconds,
            extra_env=extra_env,
        )
        print(
            f"[Search] throughput={result.throughput:.2f} req/s "
            f"avg={result.avg_latency_ms:.2f}ms p95={result.p95_ms:.2f}ms "
            f"errors={result.errors}"
        )
        results.append(result)
        return result

    current_instances = 1
    current_workers = 1
    best = benchmark(current_instances, current_workers)

    while True:
        improved_any = False

        while current_workers < args.max_workers:
            candidate = benchmark(current_instances, current_workers + 1)
            if improves(
                best,
                candidate,
                min_improvement_ratio=args.min_improvement_ratio,
                max_p95_ms=args.max_p95_ms,
            ):
                current_workers += 1
                best = candidate
                improved_any = True
                continue
            break

        if current_instances >= args.max_instances:
            break

        candidate = benchmark(current_instances + 1, current_workers)
        if improves(
            best,
            candidate,
            min_improvement_ratio=args.min_improvement_ratio,
            max_p95_ms=args.max_p95_ms,
        ):
            current_instances += 1
            best = candidate
            improved_any = True
            continue

        if not improved_any:
            break

    results_path = Path(args.results_json).resolve()
    results_path.write_text(
        json.dumps([asdict(item) for item in results], indent=2),
        encoding="utf-8",
    )

    print("\n=== Best Configuration ===")
    print(f"instances={best.instances}")
    print(f"workers={best.workers}")
    print(f"throughput={best.throughput:.2f} req/s")
    print(f"avg_latency={best.avg_latency_ms:.2f}ms")
    print(f"p95={best.p95_ms:.2f}ms")
    print(f"errors={best.errors}")
    print(f"results_json={results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
