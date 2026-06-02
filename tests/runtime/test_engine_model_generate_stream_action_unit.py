from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from democrai.core.application.ai.engine.schemas.completion import StreamChunk
from democrai.core.application.ai.pipeline_context import AiPipelineMessage
from modules.system.actions.engine.model_tests.generate_stream import (
    COMPOSER_ID,
    test_engine_model_generate_stream as run_generate_stream_action,
)


class _Effects:
    def __init__(self) -> None:
        self.property_updates: list[dict[str, Any]] = []
        self.collection_appends: list[dict[str, Any]] = []
        self.ui_message_publishes: list[dict[str, Any]] = []

    @staticmethod
    def respond(*messages):
        return {"messages": list(messages)}

    @staticmethod
    def ui_messages(messages):
        return {"ui_messages": messages}

    @staticmethod
    def notify(kind, payload):
        return {"notify": {"kind": kind, "payload": payload}}

    async def publish_property_update(
        self,
        stream_id: str,
        component_id: str,
        prop: str,
        value: Any,
        *,
        action: str | None = None,
    ):
        self.property_updates.append(
            {
                "stream_id": stream_id,
                "component_id": component_id,
                "prop": prop,
                "value": value,
                "action": action,
            }
        )

    async def publish_collection_append(
        self,
        stream_id: str,
        component_id: str,
        prop: str,
        item: dict[str, Any],
    ):
        self.collection_appends.append(
            {
                "stream_id": stream_id,
                "component_id": component_id,
                "prop": prop,
                "item": item,
            }
        )

    async def publish_ui_message(self, stream_id: str, message: dict[str, Any]):
        self.ui_message_publishes.append({"stream_id": stream_id, "message": message})


class _Table:
    @staticmethod
    def all(filters=None, sort=None):
        return {"rows": []}

    @staticmethod
    def table_model():
        return []


class _Provider:
    def __init__(self) -> None:
        self.messages = None
        self.options = None

    async def generate_stream(self, *, messages, options, on_message=None):
        self.messages = messages
        self.options = options
        if on_message is not None:
            await on_message(
                AiPipelineMessage(
                    type="llm.request",
                    pipeline_id="pipeline-1",
                    current_pipeline_id="pipeline-1",
                    request_id="request-1",
                    root_method="generate_stream",
                    name="generate_stream",
                    payload={},
                )
            )
        yield StreamChunk(id="chunk-1", delta="hel")
        yield StreamChunk(
            id="chunk-2",
            delta="lo",
            reasoning="why",
            prompt_tokens=2,
            completion_tokens=2,
            total_tokens=4,
        )


class _SDK:
    def __init__(self) -> None:
        self.provider = _Provider()

        async def _provider_by_id(_row_id: int, **_kwargs):
            return {"status": "ok", "provider": self.provider}

        async def _warmup_provider(_provider, *, wait=False):
            return None

        self.ai = SimpleNamespace(
            get_provider_by_model_registry_id=_provider_by_id,
            warmup_provider=_warmup_provider,
        )
        self.effects = _Effects()
        self.models = SimpleNamespace(ai_model_pipeline_steps=_Table())
        self.ui = SimpleNamespace(
            MessageItem=lambda component_id, **kwargs: SimpleNamespace(
                to_dict=lambda: {
                    "id": component_id,
                    "type": "MessageItem",
                    **kwargs,
                }
            ),
            Collapsible=lambda component_id, title, content="", open=False: SimpleNamespace(
                to_dict=lambda: {
                    "id": component_id,
                    "type": "Collapsible",
                    "title": title,
                    "content": content,
                    "open": open,
                }
            ),
            DataTable=lambda component_id, **kwargs: SimpleNamespace(
                to_dict=lambda: {"id": component_id, "type": "DataTable", **kwargs}
            ),
        )


@pytest.mark.asyncio
async def test_generate_stream_uses_composer_and_publishes_chunks():
    sdk = _SDK()

    result = await run_generate_stream_action(
        {
            "model_row_id": 1,
            "stream_id": "stream-1",
            COMPOSER_ID: {
                "text": "Say hello.",
                "attachments": [],
                "options": [{"key": "extra.reasoning_effort", "value": "medium"}],
                "selected_tools": ["system.test_echo"],
                "selected_skills": ["system.system_test_skill"],
                "selected_mcp": ["system_test_mcp"],
            },
        },
        sdk,
    )

    assert sdk.provider.messages == [
        {"role": "user", "content": [{"type": "text", "text": "Say hello."}]}
    ]
    assert sdk.provider.options["extra"]["reasoning_effort"] == "medium"
    assert sdk.provider.options["tools"] == ["system.test_echo"]
    assert sdk.provider.options["skills"] == ["system.system_test_skill"]
    assert sdk.provider.options["mcp"] == ["system_test_mcp"]
    assert any(item["prop"] == "text" and item["value"] == "hello" for item in sdk.effects.property_updates)
    assert any(item["prop"] == "reasoning" and item["value"] == "why" for item in sdk.effects.property_updates)
    appended_types = [item["item"]["type"] for item in sdk.effects.collection_appends]
    assert "MessageItem" in appended_types
    assert "Collapsible" in appended_types
    assert "DataTable" in appended_types
    assert result["messages"][0]["ui_messages"][0]["stateUpdate"]["values"] == {
        "/engine_model_test/generate_stream_current_request": "",
        "/engine_model_test/last_status": "ok",
    }
