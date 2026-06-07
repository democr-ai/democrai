from __future__ import annotations

from types import SimpleNamespace

import democrai.core.application.ai.orchestrator as orchestrator_mod


def test_llamacpp_provider_config_flattens_nested_runtime_defaults(monkeypatch):
    monkeypatch.setattr(
        orchestrator_mod,
        "get_engine_runtime_config",
        lambda engine_row_id: {},
    )
    monkeypatch.setattr(
        orchestrator_mod.ModelOrchestrator,
        "_catalog_model_metadata",
        lambda self, model: {
            "runtime": {
                "defaults": {
                    "generation": {
                        "temperature": 0.0,
                        "max_tokens": 8,
                    },
                    "runtime": {
                        "context_length": 512,
                        "n_gpu_layers": 0,
                    },
                }
            }
        },
    )

    model = SimpleNamespace(
        id=2,
        name="tiny-llama3-test-q2-k",
        model_path="/models/tiny-llama3-test-Q2_K.gguf",
        extra_config={},
        available_model=None,
        is_downloaded=False,
        engine=SimpleNamespace(id=1, provider="llamacpp"),
    )

    config = orchestrator_mod.ModelOrchestrator().build_provider_config(model)

    assert config["model"] == "tiny-llama3-test-q2-k"
    assert config["model_path"] == "/models/tiny-llama3-test-Q2_K.gguf"
    assert config["n_ctx"] == 512
    assert config["n_gpu_layers"] == 0
    assert "context_length" not in config
    assert "generation" not in config
    assert "runtime" not in config
