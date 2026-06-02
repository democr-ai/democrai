import asyncio
import base64
from types import SimpleNamespace

import pytest

from democrai.core.application.ai.engine.pipeline.messages import (
    materialized_pipeline_messages,
)
from democrai.core.application.ai.engine.schemas.completion import Message
from democrai.core.runtime.foundation.app import app_ctx
from engines.openai.engine import OpenAIEngine
from engines.openai_compatible.engine import OpenAICompatibleEngine
from engines.anthropic.engine import AnthropicEngine
from engines.vllm.messages import chat_messages


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8"
    "z8BQDwAFgwJ/lEN6KgAAAABJRU5ErkJggg=="
)


def test_pipeline_loads_media_storage_path_into_content_part_data(monkeypatch):
    previous_media = getattr(app_ctx(), "media", None)
    app_ctx().media = SimpleNamespace(load=lambda path: PNG_1X1)

    async def _run():
        async with materialized_pipeline_messages(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe"},
                        {"type": "image", "storage_path": "media/system/file.png"},
                    ],
                }
            ],
            engine_id="vllm",
        ) as messages:
            return messages

    try:
        messages = asyncio.run(_run())
    finally:
        app_ctx().media = previous_media

    image = messages[0].content[1]
    assert image.storage_path == "media/system/file.png"
    assert image.data == PNG_1X1


def test_vllm_chat_messages_loads_image_from_content_part_data():
    rendered = chat_messages(
        [
            Message(
                role="user",
                content=[
                    {"type": "text", "text": "describe"},
                    {"type": "image", "data": PNG_1X1, "mime_type": "image/png"},
                ],
            )
        ]
    )

    url = rendered[0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == PNG_1X1


def test_vllm_chat_messages_rejects_image_without_data():
    with pytest.raises(ValueError, match="vllm_image_data_required"):
        chat_messages([Message(role="user", content=[{"type": "image"}])])


def test_openai_formats_image_data_url():
    engine = OpenAIEngine.__new__(OpenAIEngine)

    messages = engine._format_input(
        [
            Message(
                role="user",
                content=[
                    {"type": "text", "text": "describe"},
                    {"type": "image", "data": PNG_1X1, "mime_type": "image/png"},
                ],
            )
        ]
    )

    url = messages[0]["content"][1]["image_url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == PNG_1X1


def test_openai_compatible_formats_image_data_url():
    engine = OpenAICompatibleEngine.__new__(OpenAICompatibleEngine)

    messages = engine._format_messages(
        [
            Message(
                role="user",
                content=[
                    {"type": "text", "text": "describe"},
                    {"type": "image", "data": PNG_1X1, "mime_type": "image/png"},
                ],
            )
        ]
    )

    url = messages[0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == PNG_1X1


def test_anthropic_formats_image_data_block():
    engine = AnthropicEngine.__new__(AnthropicEngine)

    message = engine._format_message(
        Message(
            role="user",
            content=[
                {"type": "text", "text": "describe"},
                {"type": "image", "data": PNG_1X1, "mime_type": "image/png"},
            ],
        )
    )

    image = message["content"][1]
    assert image["type"] == "image"
    assert image["source"]["type"] == "base64"
    assert image["source"]["media_type"] == "image/png"
    assert base64.b64decode(image["source"]["data"]) == PNG_1X1


def test_anthropic_formats_image_url_block():
    engine = AnthropicEngine.__new__(AnthropicEngine)

    message = engine._format_message(
        Message(
            role="user",
            content=[
                {"type": "image", "url": "https://example.test/image.png"},
            ],
        )
    )

    image = message["content"][0]
    assert image == {
        "type": "image",
        "source": {
            "type": "url",
            "url": "https://example.test/image.png",
        },
    }


def test_anthropic_rejects_image_without_source():
    engine = AnthropicEngine.__new__(AnthropicEngine)

    with pytest.raises(ValueError, match="anthropic_image_data_required"):
        engine._format_message(Message(role="user", content=[{"type": "image"}]))
