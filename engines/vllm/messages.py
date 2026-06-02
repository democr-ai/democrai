from __future__ import annotations

import base64
from io import BytesIO

from democrai.sdk.engines import Message


def chat_template_content_format(messages: list[Message]) -> str:
    for message in messages:
        content = message.content
        if content is None or isinstance(content, str):
            continue
        for part in content:
            if part.type.value != "text":
                return "openai"
    return "string"


def chat_messages(messages: list[Message]) -> list[dict[str, object]]:
    return [
        {
            "role": message.role.value,
            "content": _message_content(message),
        }
        for message in messages
    ]


def _message_content(message: Message) -> str | list[dict[str, object]]:
    content = message.content
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if all(part.type.value == "text" for part in content):
        return "\n".join(str(part.text or "") for part in content if part.text)
    rendered: list[dict[str, object]] = []
    for part in content:
        if part.type.value == "text":
            rendered.append({"type": "text", "text": part.text})
        elif part.type.value == "image":
            if not part.data:
                raise ValueError("vllm_image_data_required")
            from PIL import Image

            image = Image.open(BytesIO(part.data))
            image.load()
            mime = part.mime_type or "image/jpeg"
            encoded = base64.b64encode(part.data).decode("utf-8")
            rendered.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{encoded}"},
                }
            )
        elif part.type.value in {"audio", "video"}:
            raise ValueError(f"vllm_unsupported_content_type:{part.type.value}")
    return rendered
