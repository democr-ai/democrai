from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "profile_process_guard_onnx_spawn.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "profile_process_guard_onnx_spawn",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cycle_record_computes_guard_self_total_and_percent():
    mod = _load_script()

    record = mod.cycle_record(
        cycle=2,
        measured=True,
        spawn_total_ms=200.0,
        spans_ms={
            "process_guard.check_path": 90.0,
            "process_guard.check_path.self": 20.0,
            "process_guard.path_allowed.self": 30.0,
            "other": 100.0,
        },
        metrics={"process_guard.path_allowed.calls": 4.0},
    )

    assert record["cycle"] == 2
    assert record["process_guard_total_ms"] == 50.0
    assert record["process_guard_percent"] == 25.0
    assert record["error"] == ""


def test_cycle_record_preserves_error_details():
    mod = _load_script()

    record = mod.cycle_record(
        cycle=1,
        measured=True,
        spawn_total_ms=50.0,
        spans_ms={"process_guard.context.enter.self": 5.0},
        metrics={},
        error="engine_runtime_class_not_found:onnx",
        traceback_text="trace",
    )

    assert record["process_guard_total_ms"] == 5.0
    assert record["error"] == "engine_runtime_class_not_found:onnx"
    assert record["traceback"] == "trace"


def test_cycle_record_preserves_process_guard_events():
    mod = _load_script()

    record = mod.cycle_record(
        cycle=1,
        measured=True,
        spawn_total_ms=50.0,
        spans_ms={},
        metrics={},
        events={
            "process_guard.external_fs.db_check": [
                {
                    "subject_kind": "engine",
                    "subject": "onnx",
                    "operation": "read",
                    "target": "/etc/os-release",
                    "chain": [{"kind": "engine", "name": "onnx"}],
                }
            ]
        },
    )

    assert record["events"]["process_guard.external_fs.db_check"][0]["target"] == (
        "/etc/os-release"
    )


def test_aggregate_filters_process_guard_spans_and_metrics():
    mod = _load_script()
    records = [
        mod.cycle_record(
            cycle=0,
            measured=False,
            spawn_total_ms=10.0,
            spans_ms={"process_guard.check_path.self": 1000.0},
            metrics={"process_guard.path_allowed.calls": 1000.0},
        ),
        mod.cycle_record(
            cycle=1,
            measured=True,
            spawn_total_ms=100.0,
            spans_ms={
                "process_guard.check_path.self": 10.0,
                "process_guard.path_allowed.self": 5.0,
                "db.query": 200.0,
            },
            metrics={
                "process_guard.path_allowed.calls": 3.0,
                "process_guard.path_allowed.cache_hits": 2.0,
                "db.calls": 50.0,
            },
        ),
        mod.cycle_record(
            cycle=2,
            measured=True,
            spawn_total_ms=300.0,
            spans_ms={"process_guard.check_path.self": 30.0},
            metrics={"process_guard.path_allowed.calls": 7.0},
        ),
    ]

    aggregate = mod.aggregate(records, top=10)

    assert aggregate["cycles"] == 2
    assert aggregate["spawn_total_ms"]["avg"] == 200.0
    assert aggregate["process_guard_total_ms"]["avg"] == 22.5
    span_names = [item["name"] for item in aggregate["top_process_guard_spans"]]
    metric_names = [item["name"] for item in aggregate["top_process_guard_metrics"]]
    assert "process_guard.check_path.self" in span_names
    assert "db.query" not in span_names
    assert "process_guard.path_allowed.calls" in metric_names
    assert "db.calls" not in metric_names


def test_aggregate_reports_external_fs_db_check_targets():
    mod = _load_script()
    records = [
        mod.cycle_record(
            cycle=0,
            measured=False,
            spawn_total_ms=10.0,
            spans_ms={},
            metrics={},
            events={
                "process_guard.external_fs.db_check": [
                    {
                        "subject_kind": "engine",
                        "subject": "onnx",
                        "operation": "read",
                        "target": "/tmp/warmup",
                        "chain": [],
                    }
                ]
            },
        ),
        mod.cycle_record(
            cycle=1,
            measured=True,
            spawn_total_ms=10.0,
            spans_ms={},
            metrics={},
            events={
                "process_guard.external_fs.db_check": [
                    {
                        "subject_kind": "engine",
                        "subject": "onnx",
                        "operation": "read",
                        "target": "/etc/os-release",
                        "chain": [{"kind": "engine", "name": "onnx"}],
                    },
                    {
                        "subject_kind": "engine",
                        "subject": "onnx",
                        "operation": "read",
                        "target": "/etc/os-release",
                        "chain": [{"kind": "engine", "name": "onnx"}],
                    },
                    {
                        "subject_kind": "engine",
                        "subject": "onnx",
                        "operation": "read",
                        "target": "/home/fabio/data.txt",
                        "chain": [{"kind": "engine", "name": "onnx"}],
                    },
                ]
            },
        ),
    ]

    aggregate = mod.aggregate(records, top=10)
    targets = aggregate["top_external_fs_db_targets"]

    assert targets[0]["target"] == "/etc/os-release"
    assert targets[0]["count"] == 2
    assert targets[0]["category"] == "system_probe"
    assert targets[0]["chain"] == "engine:onnx"
    assert all(item["target"] != "/tmp/warmup" for item in targets)


def test_classify_external_fs_target_categories():
    mod = _load_script()

    assert mod.classify_external_fs_target("/home/me/.cache/democrai/x") == (
        "framework_runtime"
    )
    assert mod.classify_external_fs_target("/usr/lib/libcuda.so.1") == (
        "runtime_dependency"
    )
    assert mod.classify_external_fs_target("/etc/os-release") == "system_probe"
    assert mod.classify_external_fs_target("/home/me/input.txt") == "subject_io"


def test_percentile_uses_nearest_rank():
    mod = _load_script()

    assert mod.percentile([1, 2, 3, 4], 50) == 2
    assert mod.percentile([1, 2, 3, 4], 95) == 4
    assert mod.summary([]) == {
        "avg": 0.0,
        "p50": 0.0,
        "p95": 0.0,
        "min": 0.0,
        "max": 0.0,
    }


def test_build_parser_defaults_and_options():
    mod = _load_script()

    defaults = mod.build_parser().parse_args([])
    assert defaults.cycles == 5
    assert defaults.warmup == 1
    assert defaults.top == 20
    assert defaults.clear_guard_caches_each_cycle is False

    parsed = mod.build_parser().parse_args(
        [
            "--cycles",
            "2",
            "--warmup",
            "0",
            "--top",
            "3",
            "--clear-guard-caches-each-cycle",
            "--output",
            "out.json",
        ]
    )
    assert parsed.cycles == 2
    assert parsed.warmup == 0
    assert parsed.top == 3
    assert parsed.clear_guard_caches_each_cycle is True
    assert parsed.output == "out.json"
