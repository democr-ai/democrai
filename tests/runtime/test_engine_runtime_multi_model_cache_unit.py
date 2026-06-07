from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import democrai.core.application.ai.orchestrator as orchestrator_mod
import democrai.core.application.ai.engine.runtime.manager as manager_mod
from democrai.core.application.ai.orchestrator import ModelOrchestrator


class _Handle:
    def __init__(self, *, engine_id, config, model_registry_id, closed):
        self.engine_id = engine_id
        self.config = dict(config)
        self.model_registry_id = model_registry_id
        self.subject = SimpleNamespace(_process=None)
        self._closed = closed

    def close(self):
        self._closed.append(self.model_registry_id)


def test_runtime_keeps_two_models_for_same_engine_loaded(monkeypatch):
    closed = []

    def create_handle(*, engine_id, config, model_registry_id):
        return _Handle(
            engine_id=engine_id,
            config=config,
            model_registry_id=model_registry_id,
            closed=closed,
        )

    monkeypatch.setattr(manager_mod, "create_engine_handle", create_handle)
    runtime = manager_mod.EngineRuntime()

    first = runtime._ensure_handle(
        engine_row_id=1,
        model_registry_id=10,
        engine_id="engine",
        config={"model": "a"},
    )
    second = runtime._ensure_handle(
        engine_row_id=1,
        model_registry_id=11,
        engine_id="engine",
        config={"model": "b"},
    )

    assert first is not second
    assert closed == []
    assert [row["model_registry_id"] for row in runtime.active_instances()] == [10, 11]


def test_runtime_replaces_only_same_model_when_config_changes(monkeypatch):
    closed = []

    def create_handle(*, engine_id, config, model_registry_id):
        return _Handle(
            engine_id=engine_id,
            config=config,
            model_registry_id=model_registry_id,
            closed=closed,
        )

    monkeypatch.setattr(manager_mod, "create_engine_handle", create_handle)
    runtime = manager_mod.EngineRuntime()

    runtime._ensure_handle(
        engine_row_id=1,
        model_registry_id=10,
        engine_id="engine",
        config={"model": "a", "revision": 1},
    )
    runtime._ensure_handle(
        engine_row_id=1,
        model_registry_id=11,
        engine_id="engine",
        config={"model": "b"},
    )
    runtime._ensure_handle(
        engine_row_id=1,
        model_registry_id=10,
        engine_id="engine",
        config={"model": "a", "revision": 2},
    )

    assert closed == [10]
    assert sorted(row["model_registry_id"] for row in runtime.active_instances()) == [
        10,
        11,
    ]


def test_runtime_unload_model_is_granular(monkeypatch):
    closed = []

    def create_handle(*, engine_id, config, model_registry_id):
        return _Handle(
            engine_id=engine_id,
            config=config,
            model_registry_id=model_registry_id,
            closed=closed,
        )

    monkeypatch.setattr(manager_mod, "create_engine_handle", create_handle)
    runtime = manager_mod.EngineRuntime()
    for model_registry_id in (10, 11):
        runtime._ensure_handle(
            engine_row_id=1,
            model_registry_id=model_registry_id,
            engine_id="engine",
            config={"model": str(model_registry_id)},
        )

    assert runtime.unload_model(engine_row_id=1, model_registry_id=10)

    assert closed == [10]
    assert [row["model_registry_id"] for row in runtime.active_instances()] == [11]


def test_runtime_rejects_anonymous_model_handles():
    runtime = manager_mod.EngineRuntime()

    with pytest.raises(ValueError, match="engine_runtime_model_registry_id_required"):
        runtime._ensure_handle(
            engine_row_id=1,
            model_registry_id=0,
            engine_id="engine",
            config={"model": "a"},
        )


def test_runtime_guard_skips_parent_network_policy(monkeypatch):
    guard_calls = []

    @contextmanager
    def _guard(**kwargs):
        guard_calls.append(kwargs)
        yield

    monkeypatch.setattr(manager_mod, "process_guard_context", _guard)
    monkeypatch.setattr(manager_mod, "get_engine_access", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(manager_mod, "get_engine_allowed_imports", lambda *_args: [])
    monkeypatch.setattr(
        manager_mod,
        "create_engine_handle",
        lambda **kwargs: _Handle(
            engine_id=kwargs["engine_id"],
            config=kwargs["config"],
            model_registry_id=kwargs["model_registry_id"],
            closed=[],
        ),
    )

    runtime = manager_mod.EngineRuntime()
    runtime.ensure_running(
        engine_row_id=1,
        model_registry_id=10,
        engine_id="onnx",
        config={},
    )

    assert guard_calls
    assert guard_calls[0]["include_network_access"] is False


def test_active_runtime_instance_requires_matching_model_registry_id(monkeypatch):
    config = {
        "_engine_row_id": 1,
        "_model_registry_id": 20,
        "model": "same-runtime-config",
    }
    active_instance = {
        "status": "running",
        "engine_id": "engine",
        "engine_row_id": 1,
        "model_registry_id": 10,
        "config_signature": ModelOrchestrator.runtime_config_signature(config),
    }

    monkeypatch.setattr(
        orchestrator_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            engine_runtime=SimpleNamespace(active_instances=lambda: [active_instance])
        ),
    )

    assert (
        ModelOrchestrator.active_runtime_instance(
            provider_id="engine",
            config=config,
        )
        is None
    )

    active_instance["model_registry_id"] = 20

    assert ModelOrchestrator.active_runtime_instance(
        provider_id="engine",
        config=config,
    ) == active_instance
