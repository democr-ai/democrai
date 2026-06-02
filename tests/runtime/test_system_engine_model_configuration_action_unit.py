from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_model_registry_configuration_save_unloads_loaded_engine(monkeypatch):
    from modules.system.actions.engine.model_tests import configuration as mod

    row = {
        "id": 7,
        "engine_id": 42,
        "capabilities": ["speech"],
        "extra_config": {"defaults": {"runtime": {"qwen_tts_method": "voice_clone"}}},
    }
    updates = []
    unloaded = []

    monkeypatch.setattr(
        mod,
        "runtime_config_schema_for_capabilities",
        lambda _capabilities: {
            "generation_schema": {"fields": []},
            "options_schema": {"fields": []},
        },
    )

    class ModelRegistry:
        @staticmethod
        def view(row_id):
            assert row_id == 7
            return row

        @staticmethod
        def update(row_id, payload):
            updates.append((row_id, payload))
            return {**row, **payload}

    class Engines:
        @staticmethod
        async def constants():
            return {
                "model_capabilities": ["speech"],
                "output_parsers": [],
                "model_feature_schemas": {},
            }

        @staticmethod
        async def unload_loaded_model(*, engine_registry_id, model_registry_id):
            unloaded.append((engine_registry_id, model_registry_id))
            return {"unloaded": True}

    class Effects:
        @staticmethod
        def notify(channel, payload):
            return {"notify": {"channel": channel, "payload": payload}}

        @staticmethod
        def ui_messages(messages):
            return {"ui_messages": messages}

        @staticmethod
        def render():
            return {"render": True}

        @staticmethod
        def respond(*effects):
            return {"effects": effects}

    module_sdk = SimpleNamespace(
        engines=Engines(),
        models=SimpleNamespace(model_registry=ModelRegistry()),
        effects=Effects(),
        i18n=SimpleNamespace(t=lambda key: key),
    )

    await mod.save_engine_model_registry_configuration(
        {
            "model_row_id": 7,
            "form_id": "form",
            "form": {"capabilities": ["speech"]},
        },
        {},
        module_sdk,
    )

    assert updates
    assert unloaded == [(42, 7)]


@pytest.mark.asyncio
async def test_model_registry_configuration_save_persists_reasoning_extra(monkeypatch):
    from modules.system.actions.engine.model_tests import configuration as mod

    row = {
        "id": 7,
        "engine_id": 42,
        "capabilities": ["chat", "reasoning"],
        "extra_config": {"defaults": {"generation": {"extra": {}}}},
    }
    updates = []

    monkeypatch.setattr(
        mod,
        "runtime_config_schema_for_capabilities",
        lambda _capabilities: {
            "generation_schema": {"fields": []},
            "options_schema": {"fields": []},
        },
    )

    class ModelRegistry:
        @staticmethod
        def view(row_id):
            assert row_id == 7
            return row

        @staticmethod
        def update(row_id, payload):
            updates.append((row_id, payload))
            return {**row, **payload}

    class Engines:
        @staticmethod
        async def constants():
            return {
                "model_capabilities": ["chat", "reasoning"],
                "output_parsers": ["generic"],
                "model_feature_schemas": {},
            }

        @staticmethod
        async def unload_loaded_model(*, engine_registry_id, model_registry_id):
            return {"unloaded": True}

    class Effects:
        @staticmethod
        def notify(channel, payload):
            return {"notify": {"channel": channel, "payload": payload}}

        @staticmethod
        def ui_messages(messages):
            return {"ui_messages": messages}

        @staticmethod
        def render():
            return {"render": True}

        @staticmethod
        def respond(*effects):
            return {"effects": effects}

    module_sdk = SimpleNamespace(
        engines=Engines(),
        models=SimpleNamespace(model_registry=ModelRegistry()),
        effects=Effects(),
        i18n=SimpleNamespace(t=lambda key: key),
    )

    await mod.save_engine_model_registry_configuration(
        {
            "model_row_id": 7,
            "form_id": "form",
            "form": {
                "capabilities": ["chat", "reasoning"],
                "extra.reasoning_budget": 4096,
            },
        },
        {},
        module_sdk,
    )

    extra = updates[0][1]["extra_config"]["defaults"]["generation"]["extra"]
    assert extra["reasoning_budget"] == 4096


@pytest.mark.asyncio
async def test_model_registry_configuration_save_drops_empty_optional_runtime_numbers(monkeypatch):
    from modules.system.actions.engine.model_tests import configuration as mod

    row = {
        "id": 7,
        "engine_id": 42,
        "capabilities": ["reranking"],
        "extra_config": {
            "defaults": {
                "runtime": {
                    "top_k": 3,
                    "max_tokens_per_doc": 128,
                }
            }
        },
    }
    updates = []
    rerank_schema = {
        "generation_schema": {"fields": []},
        "options_schema": {
            "fields": [
                {
                    "name": "top_k",
                    "type": "integer",
                    "default": None,
                    "min": 1,
                    "step": 1,
                },
                {
                    "name": "max_tokens_per_doc",
                    "type": "number",
                    "default": None,
                    "min": 1,
                    "step": 1,
                },
            ]
        },
    }

    monkeypatch.setattr(
        mod,
        "runtime_config_schema_for_capabilities",
        lambda _capabilities: rerank_schema,
    )

    class ModelRegistry:
        @staticmethod
        def view(row_id):
            assert row_id == 7
            return row

        @staticmethod
        def update(row_id, payload):
            updates.append((row_id, payload))
            return {**row, **payload}

    class Engines:
        @staticmethod
        async def constants():
            return {
                "model_capabilities": ["reranking"],
                "output_parsers": [],
                "model_feature_schemas": {},
            }

        @staticmethod
        async def unload_loaded_model(*, engine_registry_id, model_registry_id):
            return {"unloaded": True}

    class Effects:
        @staticmethod
        def notify(channel, payload):
            return {"notify": {"channel": channel, "payload": payload}}

        @staticmethod
        def ui_messages(messages):
            return {"ui_messages": messages}

        @staticmethod
        def render():
            return {"render": True}

        @staticmethod
        def respond(*effects):
            return {"effects": effects}

    module_sdk = SimpleNamespace(
        engines=Engines(),
        models=SimpleNamespace(model_registry=ModelRegistry()),
        effects=Effects(),
        i18n=SimpleNamespace(t=lambda key: key),
    )

    await mod.save_engine_model_registry_configuration(
        {
            "model_row_id": 7,
            "form_id": "form",
            "form": {
                "capabilities": ["reranking"],
                "top_k": "",
                "max_tokens_per_doc": "",
            },
        },
        {},
        module_sdk,
    )

    runtime = updates[0][1]["extra_config"]["defaults"]["runtime"]
    assert "top_k" not in runtime
    assert "max_tokens_per_doc" not in runtime
