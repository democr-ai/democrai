from __future__ import annotations

from types import SimpleNamespace

from democrai.core.application.ai.orchestrator import ModelOrchestrator
import democrai.core.application.ai.orchestrator as orchestrator_mod


def test_unload_candidates_include_engine_runtime_instances(monkeypatch):
    orch = ModelOrchestrator()
    runtime = SimpleNamespace(
        active_instances=lambda: [
            {
                "engine_row_id": 9,
                "engine_id": "vllm",
                "model": "gpt-oss",
                "model_registry_id": 11,
                "status": "running",
            },
            {"engine_row_id": 10, "status": "stopped"},
        ]
    )
    monkeypatch.setattr(
        orchestrator_mod,
        "app_ctx",
        lambda: SimpleNamespace(engine_runtime=runtime),
    )
    monkeypatch.setattr(
        orchestrator_mod,
        "genai_manager",
        SimpleNamespace(list_loaded_instance_ids=lambda: ["legacy-instance"]),
    )

    assert orch._find_unload_candidates(1, 1) == [
        {
            "engine_row_id": 9,
            "engine_id": "vllm",
            "model": "gpt-oss",
            "model_registry_id": 11,
        },
        "legacy-instance",
    ]


def test_unload_candidates_use_runtime_unload_for_engine_instances(monkeypatch):
    orch = ModelOrchestrator()
    runtime_unloaded = []
    manager_unloaded = []
    runtime = SimpleNamespace(
        unload_model=lambda *, engine_row_id, model_registry_id: runtime_unloaded.append(
            (engine_row_id, model_registry_id)
        )
        or True
    )
    monkeypatch.setattr(
        orchestrator_mod,
        "app_ctx",
        lambda: SimpleNamespace(engine_runtime=runtime),
    )
    monkeypatch.setattr(
        orchestrator_mod,
        "genai_manager",
        SimpleNamespace(
            unload_model=lambda instance_id: manager_unloaded.append(instance_id)
        ),
    )

    orch._unload_candidates(
        [
            {"engine_row_id": 9, "model_registry_id": 11, "model": "gpt-oss"},
            "legacy-instance",
        ]
    )

    assert runtime_unloaded == [(9, 11)]
    assert manager_unloaded == ["legacy-instance"]
