from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.system.actions.engine.model_tests.generate_completion import (
    COMPOSER_ID,
    test_engine_model_generate_completion as run_engine_model_generate_completion,
)


class _Provider:
    def __init__(self) -> None:
        self.messages = None
        self.options = None

    async def generate_completion(
        self,
        *,
        messages,
        options,
        on_response=None,
        on_error=None,
        on_message=None,
    ):
        self.messages = messages
        self.options = options
        return SimpleNamespace(id="request-1", pipeline_id="pipeline-1")


class _Effects:
    def __init__(self) -> None:
        self.property_updates = []
        self.collection_appends = []
        self.ui_messages_published = []

    @staticmethod
    def respond(*messages):
        return {"messages": list(messages)}

    @staticmethod
    def ui_messages(messages):
        return {"ui_messages": messages}

    @staticmethod
    def notify(channel, payload):
        return {"notify": {"channel": channel, **payload}}

    @staticmethod
    def render():
        return {"render": True}

    async def publish_property_update(
        self,
        stream_id,
        component_id,
        prop,
        value,
        *,
        action=None,
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

    async def publish_collection_append(self, stream_id, component_id, prop, item):
        self.collection_appends.append(
            {
                "stream_id": stream_id,
                "component_id": component_id,
                "prop": prop,
                "item": item,
            }
        )

    async def publish_ui_message(self, stream_id, message):
        self.ui_messages_published.append(
            {
                "stream_id": stream_id,
                "message": message,
            }
        )


class _Table:
    @staticmethod
    def all(filters=None, sort=None):
        return {"rows": []}

    @staticmethod
    def table_model():
        return []


def _sdk(provider):
    async def _warmup_provider(_provider, *, wait=False):
        return None

    return SimpleNamespace(
        ai=SimpleNamespace(
            get_provider_by_model_registry_id=lambda _row_id: {
                "status": "ok",
                "provider": provider,
            },
            warmup_provider=_warmup_provider,
        ),
        effects=_Effects(),
        models=SimpleNamespace(ai_model_pipeline_steps=_Table()),
        ui=SimpleNamespace(
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
                to_dict=lambda: {
                    "id": component_id,
                    "type": "DataTable",
                    **kwargs,
                }
            ),
            MessageItem=lambda component_id, **kwargs: SimpleNamespace(
                to_dict=lambda: {
                    "id": component_id,
                    "type": "MessageItem",
                    **kwargs,
                }
            ),
        ),
    )


async def _get_provider_by_model_registry_id(provider, _row_id):
    return {"status": "ok", "provider": provider}


def _module_sdk(provider):
    sdk = _sdk(provider)
    sdk.ai.get_provider_by_model_registry_id = lambda row_id: _get_provider_by_model_registry_id(
        provider,
        row_id,
    )
    return sdk


@pytest.mark.asyncio
async def test_generate_completion_passes_attachment_storage_path_to_provider():
    provider = _Provider()
    sdk = _module_sdk(provider)

    await run_engine_model_generate_completion(
        {
            "model_row_id": 1,
            "stream_id": "stream-1",
            COMPOSER_ID: {
                "text": "describe",
                "attachments": [
                    {
                        "content_type": "image/png",
                        "storage_path": "media/system/file.png",
                    }
                ],
                "options": [],
                "selected_tools": [],
                "selected_skills": [],
                "selected_mcp": [],
            },
        },
        sdk,
    )

    assert provider.messages == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe"},
                {
                    "type": "image",
                    "mime_type": "image/png",
                    "storage_path": "media/system/file.png",
                },
            ],
        }
    ]
    assert provider.options == {"tools": [], "skills": [], "mcp": []}
