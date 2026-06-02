from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from modules.system.actions.engine.model_tests.generate_completion import (
    COMPOSER_ID,
    _pipeline_steps_table,
    test_engine_model_generate_completion as run_generate_completion_action,
)


class _Effects:
    def __init__(self) -> None:
        self.property_updates: list[dict[str, Any]] = []
        self.collection_appends: list[dict[str, Any]] = []
        self.published_ui_messages: list[dict[str, Any]] = []

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
        self.published_ui_messages.append({"stream_id": stream_id, "message": message})


class _Provider:
    def __init__(self) -> None:
        self.options = None

    async def generate_completion(self, *, messages, options, **_kwargs):
        self.options = options
        return SimpleNamespace(id="request-1", pipeline_id="pipeline-1")


class _Table:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def all(self, **kwargs):
        self.calls.append(kwargs)
        return {"rows": []}

    def table_model(self):
        return {"name": "ai_model_pipeline_steps"}


class _SDK:
    def __init__(self, *, provider_result: dict[str, Any] | None = None) -> None:
        self.provider = _Provider()

        async def _provider(_row_id: int):
            if provider_result is not None:
                return provider_result
            return {
                "status": "need_confirmation",
                "to_unload": ["engine_3__qwen3.5-9b-unsloth-q4-k-m"],
            }

        async def _warmup_provider(_provider, *, wait=False):
            return None

        self.ai = SimpleNamespace(
            get_provider_by_model_registry_id=_provider,
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
async def test_generate_completion_reports_provider_confirmation_without_keyerror():
    sdk = _SDK()

    result = await run_generate_completion_action(
        {
            "model_row_id": 1,
            "stream_id": "stream-1",
            COMPOSER_ID: {
                "text": "Reply with one short sentence.",
                "attachments": [],
                "options": [],
                "selected_tools": [],
                "selected_skills": [],
                "selected_mcp": [],
            },
        },
        sdk,
    )

    assert sdk.effects.property_updates[0]["action"] == "set"
    appended_items = [entry["item"] for entry in sdk.effects.collection_appends]
    error_item = next(
        item for item in appended_items if "provider error" in item.get("title", "")
    )
    assert "need_confirmation" in error_item["content"]
    assert result["messages"][0]["ui_messages"][0]["stateUpdate"]["values"] == {
        "/engine_model_test/generate_completion_current_request": "",
        "/engine_model_test/last_status": "error",
    }


@pytest.mark.asyncio
async def test_generate_completion_nests_extra_composer_options():
    sdk = _SDK(provider_result={"status": "ok", "provider": None})
    sdk.ai = SimpleNamespace(
        get_provider_by_model_registry_id=lambda _row_id: _async_result(
            {"status": "ok", "provider": sdk.provider}
        ),
        warmup_provider=lambda _provider, *, wait=False: _async_result(None),
    )

    await run_generate_completion_action(
        {
            "model_row_id": 1,
            "stream_id": "stream-1",
            COMPOSER_ID: {
                "text": "Reply with one short sentence.",
                "attachments": [],
                "options": [{"key": "extra.reasoning_effort", "value": "medium"}],
                "selected_tools": [],
                "selected_skills": [],
                "selected_mcp": [],
            },
        },
        sdk,
    )

    assert sdk.provider.options["extra"]["reasoning_effort"] == "medium"


def test_pipeline_steps_table_does_not_query_without_pipeline_id():
    sdk = _SDK()

    table = _pipeline_steps_table(sdk, "").to_dict()

    assert table["rows"] == []
    assert sdk.models.ai_model_pipeline_steps.calls == []


async def _async_result(value: Any) -> Any:
    return value
