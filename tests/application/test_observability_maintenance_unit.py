from __future__ import annotations

from types import SimpleNamespace

from democrai.core.application.observability.maintenance import ObservabilityMaintenanceService


def test_observability_maintenance_service_runs_cycle_and_shutdown(monkeypatch):
    events = []

    class _Stop:
        def __init__(self):
            self.calls = 0

        def is_set(self):
            return self.calls > 0

        def wait(self, _seconds):
            self.calls += 1

        def set(self):
            self.calls = 1

    class _Thread:
        def __init__(self, target, name, daemon):
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False

        def start(self):
            self.started = True
            self.target()

        def is_alive(self):
            return False

        def join(self, timeout):
            events.append(("join", timeout))

    monkeypatch.setattr("threading.Event", _Stop)
    monkeypatch.setattr("threading.Thread", _Thread)

    service = ObservabilityMaintenanceService(
        store=SimpleNamespace(
            flush_export_outbox=lambda limit=100: events.append(("flush", limit)),
            process_trace_archive_queue=lambda **kwargs: events.append(("trace", kwargs)),
            apply_retention=lambda **kwargs: events.append(("retention", kwargs)),
        ),
        logger=SimpleNamespace(error=lambda message: events.append(("error", message))),
        events_days=30,
        audit_days=180,
        ai_model_usage_days=90,
        export_outbox_days=14,
        trace_archive_queue_days=7,
        cleanup_interval_seconds=60,
        outbox_flush_interval_seconds=30,
    )

    service.start()
    service.shutdown()

    assert events[0] == ("flush", 200)
    assert events[1][0] == "trace"
    assert events[2][0] == "retention"


def test_observability_maintenance_service_handles_errors_and_idempotent_start(monkeypatch):
    events = []

    class _Stop:
        def __init__(self):
            self.wait_calls = 0
            self.stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, _seconds):
            self.wait_calls += 1
            self.stopped = True

        def set(self):
            self.stopped = True

    class _Thread:
        def __init__(self, target, name, daemon):
            self.target = target
            self.started = False
            self._alive = True

        def start(self):
            self.started = True
            self.target()
            self._alive = False

        def is_alive(self):
            return self._alive

        def join(self, timeout):
            events.append(("join", timeout))

    monkeypatch.setattr("threading.Event", _Stop)
    monkeypatch.setattr("threading.Thread", _Thread)

    service = ObservabilityMaintenanceService(
        store=SimpleNamespace(
            flush_export_outbox=lambda limit=100: (_ for _ in ()).throw(RuntimeError("boom")),
            process_trace_archive_queue=lambda **kwargs: events.append(("trace", kwargs)),
            apply_retention=lambda **kwargs: events.append(("retention", kwargs)),
        ),
        logger=SimpleNamespace(error=lambda message: events.append(("error", message))),
        events_days=30,
        audit_days=180,
        ai_model_usage_days=90,
        export_outbox_days=14,
        trace_archive_queue_days=7,
        cleanup_interval_seconds=0,
        outbox_flush_interval_seconds=0,
    )

    service.start()
    # second start must be ignored
    service.start()
    service._thread._alive = True
    service.shutdown()

    assert any(item[0] == "error" and "boom" in item[1] for item in events)
    assert ("join", 2) in events


def test_observability_maintenance_retention_runs_on_its_own_interval(monkeypatch):
    events = []
    monotonic_values = iter([0.0, 1.0, 2.0, 3.0, 4.0])

    class _Stop:
        def __init__(self):
            self.wait_calls = 0
            self.stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, _seconds):
            self.wait_calls += 1
            if self.wait_calls >= 3:
                self.stopped = True

        def set(self):
            self.stopped = True

    class _Thread:
        def __init__(self, target, name, daemon):
            self.target = target
            self.started = False
            self._alive = True

        def start(self):
            self.started = True
            self.target()
            self._alive = False

        def is_alive(self):
            return self._alive

        def join(self, timeout):
            events.append(("join", timeout))

    monkeypatch.setattr("threading.Event", _Stop)
    monkeypatch.setattr("threading.Thread", _Thread)
    monkeypatch.setattr(
        "democrai.core.application.observability.maintenance.time.monotonic",
        lambda: next(monotonic_values),
    )

    service = ObservabilityMaintenanceService(
        store=SimpleNamespace(
            flush_export_outbox=lambda limit=100: events.append(("flush", limit)),
            process_trace_archive_queue=lambda **kwargs: events.append(("trace", kwargs)),
            apply_retention=lambda **kwargs: events.append(("retention", kwargs)),
        ),
        logger=SimpleNamespace(error=lambda message: events.append(("error", message))),
        events_days=30,
        audit_days=180,
        ai_model_usage_days=90,
        export_outbox_days=14,
        trace_archive_queue_days=7,
        cleanup_interval_seconds=10,
        outbox_flush_interval_seconds=1,
    )

    service.start()
    service.shutdown()

    assert len([item for item in events if item[0] == "flush"]) == 3
    assert len([item for item in events if item[0] == "retention"]) == 1


def test_observability_maintenance_handles_retention_error_and_logger_none(monkeypatch):
    events = []
    monotonic_values = iter([0.0, 1.0])

    class _Stop:
        def __init__(self):
            self.stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, _seconds):
            self.stopped = True

        def set(self):
            self.stopped = True

    class _Thread:
        def __init__(self, target, name, daemon):
            self.target = target
            self._alive = True

        def start(self):
            self.target()
            self._alive = False

        def is_alive(self):
            return self._alive

        def join(self, timeout):
            events.append(("join", timeout))

    monkeypatch.setattr("threading.Event", _Stop)
    monkeypatch.setattr("threading.Thread", _Thread)
    monkeypatch.setattr(
        "democrai.core.application.observability.maintenance.time.monotonic",
        lambda: next(monotonic_values),
    )

    # flush raises with logger=None -> branch must be silent
    service_silent = ObservabilityMaintenanceService(
        store=SimpleNamespace(
            flush_export_outbox=lambda limit=100: (_ for _ in ()).throw(RuntimeError("flush boom")),
            process_trace_archive_queue=lambda **kwargs: None,
            apply_retention=lambda **kwargs: None,
        ),
        logger=None,
        events_days=30,
        audit_days=180,
        ai_model_usage_days=90,
        export_outbox_days=14,
        trace_archive_queue_days=7,
        cleanup_interval_seconds=1,
        outbox_flush_interval_seconds=1,
    )
    service_silent.start()
    service_silent.shutdown()

    monotonic_values_none_ret = iter([0.0, 1.0])
    monkeypatch.setattr(
        "democrai.core.application.observability.maintenance.time.monotonic",
        lambda: next(monotonic_values_none_ret),
    )
    service_retention_silent = ObservabilityMaintenanceService(
        store=SimpleNamespace(
            flush_export_outbox=lambda limit=100: None,
            process_trace_archive_queue=lambda **kwargs: None,
            apply_retention=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("retention silent boom")),
        ),
        logger=None,
        events_days=30,
        audit_days=180,
        ai_model_usage_days=90,
        export_outbox_days=14,
        trace_archive_queue_days=7,
        cleanup_interval_seconds=1,
        outbox_flush_interval_seconds=1,
    )
    service_retention_silent.start()
    service_retention_silent.shutdown()

    monotonic_values2 = iter([0.0, 1.0])
    monkeypatch.setattr(
        "democrai.core.application.observability.maintenance.time.monotonic",
        lambda: next(monotonic_values2),
    )

    # retention raises with logger available -> error must be logged
    service_logged = ObservabilityMaintenanceService(
        store=SimpleNamespace(
            flush_export_outbox=lambda limit=100: None,
            process_trace_archive_queue=lambda **kwargs: None,
            apply_retention=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("retention boom")),
        ),
        logger=SimpleNamespace(error=lambda message: events.append(("error", message))),
        events_days=30,
        audit_days=180,
        ai_model_usage_days=90,
        export_outbox_days=14,
        trace_archive_queue_days=7,
        cleanup_interval_seconds=1,
        outbox_flush_interval_seconds=1,
    )
    service_logged.start()
    service_logged.shutdown()

    assert any(item[0] == "error" and "retention boom" in item[1] for item in events)
