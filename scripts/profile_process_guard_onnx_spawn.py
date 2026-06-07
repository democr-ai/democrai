from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = max(
        0,
        min(
            len(ordered) - 1,
            math.ceil((float(percentile_value) / 100.0) * len(ordered)) - 1,
        ),
    )
    return ordered[index]


def summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}
    return {
        "avg": sum(values) / len(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "min": min(values),
        "max": max(values),
    }


def process_guard_self_total(spans_ms: dict[str, float]) -> float:
    self_values = [
        float(value)
        for name, value in spans_ms.items()
        if name.startswith("process_guard.") and name.endswith(".self")
    ]
    if self_values:
        return sum(self_values)
    return sum(
        float(value)
        for name, value in spans_ms.items()
        if name.startswith("process_guard.")
    )


def top_prefixed(
    values: dict[str, float],
    *,
    prefix: str,
    limit: int,
) -> list[dict[str, float | str]]:
    rows = [
        {"name": name, "value": float(value)}
        for name, value in values.items()
        if name.startswith(prefix)
    ]
    return sorted(rows, key=lambda item: float(item["value"]), reverse=True)[:limit]


def cycle_record(
    *,
    cycle: int,
    measured: bool,
    spawn_total_ms: float,
    spans_ms: dict[str, float],
    metrics: dict[str, float],
    error: str | None = None,
    traceback_text: str | None = None,
) -> dict[str, Any]:
    guard_total_ms = process_guard_self_total(spans_ms)
    return {
        "cycle": int(cycle),
        "measured": bool(measured),
        "spawn_total_ms": float(spawn_total_ms),
        "process_guard_total_ms": guard_total_ms,
        "process_guard_percent": (
            (guard_total_ms / float(spawn_total_ms)) * 100.0
            if spawn_total_ms > 0
            else 0.0
        ),
        "spans_ms": dict(spans_ms),
        "metrics": dict(metrics),
        "error": str(error or ""),
        "traceback": str(traceback_text or ""),
    }


def aggregate(records: list[dict[str, Any]], *, top: int) -> dict[str, Any]:
    measured = [record for record in records if bool(record.get("measured"))]
    aggregate_spans: dict[str, float] = {}
    aggregate_metrics: dict[str, float] = {}
    for record in measured:
        for name, value in dict(record.get("spans_ms") or {}).items():
            aggregate_spans[name] = aggregate_spans.get(name, 0.0) + float(value)
        for name, value in dict(record.get("metrics") or {}).items():
            aggregate_metrics[name] = aggregate_metrics.get(name, 0.0) + float(value)
    return {
        "cycles": len(measured),
        "spawn_total_ms": summary(
            [float(record.get("spawn_total_ms") or 0.0) for record in measured]
        ),
        "process_guard_total_ms": summary(
            [float(record.get("process_guard_total_ms") or 0.0) for record in measured]
        ),
        "process_guard_percent": summary(
            [float(record.get("process_guard_percent") or 0.0) for record in measured]
        ),
        "top_process_guard_spans": top_prefixed(
            aggregate_spans,
            prefix="process_guard.",
            limit=top,
        ),
        "top_process_guard_metrics": top_prefixed(
            aggregate_metrics,
            prefix="process_guard.",
            limit=top,
        ),
    }


def clear_guard_caches() -> None:
    from democrai.core.infrastructure.sandbox import process_guard

    clear = getattr(process_guard, "_clear_path_resolution_caches", None)
    if not callable(clear):
        raise RuntimeError("process_guard_clear_path_resolution_caches_unavailable")
    clear()


def configure_runtime_engine_paths() -> None:
    from democrai.core.application.ai.engine import manifests
    from democrai.core.runtime.foundation.app import app_ctx
    from democrai.core.runtime.foundation.paths import ENGINES_PATH_ENV

    engine_root = ROOT / "engines"
    if not engine_root.is_dir():
        raise RuntimeError(f"engine_root_not_found:{engine_root}")
    resolved = str(engine_root.resolve())
    app_ctx().runtime_engine_paths = (resolved,)
    manifests.list_engine_manifests.cache_clear()

    current = [item for item in str(os.environ.get(ENGINES_PATH_ENV) or "").split(os.pathsep) if item]
    if resolved not in current:
        os.environ[ENGINES_PATH_ENV] = os.pathsep.join([resolved, *current])


def run_cycle(
    *,
    cycle: int,
    measured: bool,
    clear_caches: bool,
) -> dict[str, Any]:
    from democrai.core.runtime.observability import profiling
    from democrai.core.application.ai.engine.runtime.access import (
        get_engine_access,
        get_engine_allowed_imports,
    )
    from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
    from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject

    if clear_caches:
        clear_guard_caches()

    profiler = profiling.RequestProfiler(
        request_id=f"onnx-spawn-{cycle}",
        request_kind="engine_spawn",
        enabled=True,
    )
    token = profiling._current_profiler.set(profiler)
    subject = EngineWorkerSubject.__new__(EngineWorkerSubject)
    error = ""
    traceback_text = ""
    started_at = time.perf_counter()
    try:
        with process_guard_context(
            subject="onnx",
            subject_kind="engine",
            access=get_engine_access("onnx", "runtime", config={}),
            allowed_imports=get_engine_allowed_imports("onnx", "runtime"),
            allow_subprocess=True,
            allow_fork=True,
            include_network_access=False,
        ):
            EngineWorkerSubject.__init__(
                subject,
                engine_id="onnx",
                config={},
                class_only=True,
            )
    except Exception as exc:
        error = str(exc)
        traceback_text = traceback.format_exc()
    finally:
        try:
            if subject is not None:
                close = getattr(subject, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception as exc:
                        if not error:
                            error = f"close_failed:{exc}"
                            traceback_text = traceback.format_exc()
        finally:
            spawn_total_ms = (time.perf_counter() - started_at) * 1000.0
            profiling._current_profiler.reset(token)
    return cycle_record(
        cycle=cycle,
        measured=measured,
        spawn_total_ms=spawn_total_ms,
        spans_ms=profiler.spans_ms,
        metrics=profiler.metrics,
        error=error,
        traceback_text=traceback_text,
    )


def print_report(payload: dict[str, Any], *, top: int) -> None:
    records = [record for record in payload["records"] if bool(record.get("measured"))]
    for record in records:
        print(
            "cycle={cycle} spawn={spawn:.2f}ms guard={guard:.2f}ms guard={percent:.2f}%{error}".format(
                cycle=record["cycle"],
                spawn=record["spawn_total_ms"],
                guard=record["process_guard_total_ms"],
                percent=record["process_guard_percent"],
                error=f" error={record['error'].splitlines()[0]}" if record.get("error") else "",
            )
        )

    aggregate_payload = payload["aggregate"]
    spawn = aggregate_payload["spawn_total_ms"]
    guard = aggregate_payload["process_guard_total_ms"]
    percent = aggregate_payload["process_guard_percent"]
    print(
        "summary spawn_avg={:.2f}ms spawn_p50={:.2f}ms spawn_p95={:.2f}ms".format(
            spawn["avg"],
            spawn["p50"],
            spawn["p95"],
        )
    )
    print(
        "summary guard_avg={:.2f}ms guard_p50={:.2f}ms guard_p95={:.2f}ms guard_percent_avg={:.2f}%".format(
            guard["avg"],
            guard["p50"],
            guard["p95"],
            percent["avg"],
        )
    )

    print(f"top {top} process_guard spans")
    for item in aggregate_payload["top_process_guard_spans"]:
        print(f"  {item['name']}={item['value']:.2f}ms")

    print(f"top {top} process_guard metrics")
    for item in aggregate_payload["top_process_guard_metrics"]:
        print(f"  {item['name']}={item['value']:.0f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Profile process_guard cost while spawning ONNX engine worker.",
    )
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--clear-guard-caches-each-cycle", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--top", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cycles = max(1, int(args.cycles))
    warmup = max(0, int(args.warmup))
    top = max(1, int(args.top))
    configure_runtime_engine_paths()

    records = []
    for cycle in range(warmup + cycles):
        measured = cycle >= warmup
        records.append(
            run_cycle(
                cycle=cycle,
                measured=measured,
                clear_caches=bool(args.clear_guard_caches_each_cycle),
            )
        )

    payload = {
        "engine_id": "onnx",
        "mode": "class_only",
        "cycles": cycles,
        "warmup": warmup,
        "clear_guard_caches_each_cycle": bool(args.clear_guard_caches_each_cycle),
        "records": records,
        "aggregate": aggregate(records, top=top),
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    print_report(payload, top=top)
    measured_errors = [
        record for record in records if record.get("measured") and record.get("error")
    ]
    return 1 if measured_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
