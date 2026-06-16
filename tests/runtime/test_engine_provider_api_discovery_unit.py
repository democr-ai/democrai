from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_provider_api_discovery_uses_engine_action_without_model_runtime(monkeypatch):
    import democrai.core.application.ai.models.instance_models as mod

    calls = []

    monkeypatch.setattr(
        mod,
        "_engine_row",
        lambda engine_id: SimpleNamespace(
            id=int(engine_id),
            provider="openai_compatible",
            config={"base_url": "https://example.test/v1"},
        ),
    )
    monkeypatch.setattr(
        mod,
        "get_engine_manifest",
        lambda provider: {
            "provider": {
                "id": provider,
                "deployment": "remote",
                "model_source": "provider_api",
            }
        },
    )
    monkeypatch.setattr(mod, "decrypt_provider_config", lambda provider, config: dict(config))
    monkeypatch.setattr(mod, "list_engine_models", lambda provider: [])
    async def refresh_allowlist(provider):
        return None

    monkeypatch.setattr(mod, "_refresh_local_network_allowlist_for_engine", refresh_allowlist)

    class Provider:
        def invoke_engine_action(self, **kwargs):
            calls.append(kwargs)
            return [
                {
                    "id": "runtime-model",
                    "label": "Runtime Model",
                    "capabilities": ["chat"],
                    "format": "remote",
                }
            ]

    monkeypatch.setattr(
        "democrai.core.infrastructure.ai.engine.invocation.orchestrator.EngineOrchestratorProviderResolver",
        lambda: SimpleNamespace(provider=lambda: Provider()),
    )

    rows = await mod.list_available_models_for_engine(9)

    assert calls == [
        {
            "engine_registry_id": 9,
            "engine_id": "openai_compatible",
            "config": {"base_url": "https://example.test/v1"},
            "method": "list_available_models",
            "payload": {},
        }
    ]
    assert rows[0]["id"] == "runtime-model"
