from __future__ import annotations

from typing import Any

from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required

from modules.system.actions.engine.model_tests.common import run_simple_provider_test
from modules.system.utils.actions.engine.model_test_support import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    _number_value,
    _response_text,
    _upload_mime,
    _upload_public_url,
    _upload_storage_path,
)


@action("test_engine_model_multimodal")
@permission_required(["system.engine.model.manage"])
async def test_engine_model_multimodal(ctx: dict[str, Any], module_sdk):
    media_source = ""
    media_kind = ""

    async def execute(test_ctx, provider):
        nonlocal media_source, media_kind
        content: list[dict[str, Any]] = [{"type": "text", "text": test_ctx.prompt}]
        media_path = _upload_storage_path(test_ctx.payload, "media")
        if media_path:
            media_mime = _upload_mime(test_ctx.payload, "media")
            media_source = _upload_public_url(module_sdk, test_ctx.payload, "media")
            media_kind = (
                "image"
                if media_mime.lower().startswith("image/")
                else "audio"
                if media_mime.lower().startswith("audio/")
                else "video"
                if media_mime.lower().startswith("video/")
                else ""
            )
            content_type = (
                "image"
                if media_mime.lower().startswith("image/")
                else "audio"
                if media_mime.lower().startswith("audio/")
                else "video"
            )
            content.append(
                {
                    "type": content_type,
                    "data": bytes(module_sdk.media.view(media_path)),
                    "mime_type": media_mime,
                }
            )
        response = await provider.generate_completion(
            messages=[{"role": "user", "content": content}],
            options={
                "temperature": _number_value(test_ctx.generation.get("temperature"), DEFAULT_TEMPERATURE),
                "top_p": _number_value(test_ctx.generation.get("top_p"), DEFAULT_TOP_P),
                "max_tokens": (
                    int(test_ctx.generation["max_tokens"])
                    if test_ctx.generation.get("max_tokens") not in (None, "")
                    else None
                ),
            },
        )
        return response, _response_text(response), None

    def enrich(result: dict[str, Any]) -> None:
        if media_source:
            result["media_source"] = media_source
            result["media_kind"] = media_kind

    return await run_simple_provider_test(
        ctx,
        module_sdk,
        method="multimodal",
        require_prompt=True,
        execute=execute,
        enrich_result=enrich,
    )
