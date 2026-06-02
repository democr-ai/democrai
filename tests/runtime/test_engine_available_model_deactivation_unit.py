from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_deactivate_engine_model_updates_available_models_store():
    from modules.system.actions.engine.available_models import activation as mod

    updated = []

    class ModelRegistry:
        @staticmethod
        def view(row_id):
            assert row_id == 7
            return {"id": 7, "status": "active"}

        @staticmethod
        def update(row_id, payload):
            updated.append((row_id, payload))
            return {"id": row_id, **payload}

    class Effects:
        @staticmethod
        def ui_messages(messages):
            return {"ui_messages": messages}

        @staticmethod
        def notify(channel, payload):
            return {"notify": {"channel": channel, "payload": payload}}

        @staticmethod
        def render():
            return {"render": True}

        @staticmethod
        def respond(*effects):
            return {"effects": effects}

    module_sdk = SimpleNamespace(
        models=SimpleNamespace(model_registry=ModelRegistry()),
        effects=Effects(),
        i18n=SimpleNamespace(t=lambda key, context=None: key),
        system=SimpleNamespace(log=lambda message, level: None),
    )

    response = await mod.deactivate_engine_model(
        {
            "model_row_id": 7,
            "items": [
                {
                    "model_id": "active-model",
                    "model_row_id": 7,
                    "activated": True,
                    "icon": "ric.checkbox-circle-line",
                    "icon_color": "#22C55E",
                    "search_text": "active-model chat",
                },
                {
                    "model_id": "other-model",
                    "model_row_id": 9,
                    "activated": True,
                    "icon": "ric.checkbox-circle-line",
                    "icon_color": "#22C55E",
                    "search_text": "other-model chat",
                },
            ],
            "engine_models_available_name_filter": "",
            "engine_models_available_capability_filter": "",
        },
        {},
        module_sdk,
    )

    state_update = response["effects"][0]["ui_messages"][0]["stateUpdate"]["values"]

    assert updated == [(7, {"status": "available"})]
    assert state_update["/engine_models_available/all"][0]["activated"] is False
    assert state_update["/engine_models_available/all"][0]["model_row_id"] is None
    assert state_update["/engine_models_available/all"][1]["model_row_id"] == 9
    assert "render" not in response["effects"][0]
