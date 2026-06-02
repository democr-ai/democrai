from __future__ import annotations

from typing import Any

from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required

from modules.system.actions.engine.model_tests.common import get_provider, load_context
from modules.system.actions.engine.model_tests.structured_result import (
    append_structured_error,
    append_structured_success,
    append_structured_trace,
    clear_structured_result,
    update_structured_status,
)
from modules.system.utils.actions.engine.model_test_support import (
    _bool_payload,
    _media_bytes_from_upload,
    _optional_int_value,
    _upload_mime,
    _upload_public_url,
)


@action("test_engine_model_detect")
@permission_required(["system.engine.model.manage"])
async def test_engine_model_detect(ctx: dict[str, Any], module_sdk):
    method = "detect"
    stream_id = str(ctx.get("stream_id") or "")
    test_ctx = load_context(ctx, module_sdk, require_prompt=False)
    if test_ctx is None:
        return module_sdk.effects.respond(module_sdk.effects.render())
    if not stream_id:
        raise RuntimeError("stream_id_required")

    await clear_structured_result(module_sdk, stream_id)
    try:
        media_bytes = _media_bytes_from_upload(module_sdk, test_ctx.payload, "media")
        media_mime = _upload_mime(test_ctx.payload, "media").lower()
        media_source = _upload_public_url(module_sdk, test_ctx.payload, "media")
        media_kind = (
            "image"
            if media_mime.startswith("image/")
            else "video"
            if media_mime.startswith("video/")
            else ""
        )
        detect_options = {
            key: test_ctx.payload[key]
            for key in (
                "conf",
                "iou",
                "slice_width",
                "slice_height",
                "overlap_height_ratio",
                "overlap_width_ratio",
                "mode",
                "tracker",
                "classes",
            )
            if key in test_ctx.payload and test_ctx.payload.get(key) not in (None, "")
        }
        if "with_sahi" in test_ctx.payload and test_ctx.payload.get("with_sahi") not in (None, ""):
            detect_options["with_sahi"] = _bool_payload(test_ctx.payload.get("with_sahi"))
        if (
            str(detect_options.get("mode") or "").strip().lower() == "track"
            and not media_mime.startswith("video/")
        ):
            raise ValueError("detect_tracking_requires_video")

        await append_structured_trace(
            module_sdk,
            stream_id,
            method=method,
            label="detect request",
            payload={
                "model_row_id": test_ctx.row_id,
                "media_kind": media_kind,
                "options": detect_options,
            },
        )
        provider, warmup_ms, provider_error = await get_provider(module_sdk, test_ctx.row_id)
        if provider is None:
            await append_structured_error(
                module_sdk,
                stream_id,
                method=method,
                message=provider_error,
            )
            await update_structured_status(module_sdk, stream_id, "error")
            return module_sdk.effects.respond(
                module_sdk.effects.notify(
                    "toast",
                    {"level": "error", "message": provider_error},
                )
            )
        await append_structured_trace(
            module_sdk,
            stream_id,
            method=method,
            label="provider ready",
            payload={"warmup_ms": warmup_ms},
        )
        await append_structured_trace(
            module_sdk,
            stream_id,
            method=method,
            label="engine call started",
            payload={
                "method": method,
                "media_kind": media_kind,
                "options": detect_options,
            },
        )
        response = await provider.detect(
            image_data=media_bytes if media_mime.startswith("image/") else None,
            video_data=None if media_mime.startswith("image/") else media_bytes,
            frame_index=_optional_int_value(test_ctx.payload.get("frame_index")) or 0,
            **detect_options,
        )
        detections = (
            response.get("xyxy")
            if isinstance(response, dict)
            else getattr(response, "xyxy", None)
        )
        result = response.model_dump(mode="python") if hasattr(response, "model_dump") else response
        if isinstance(result, dict) and media_source:
            result = {**result, "media_source": media_source, "media_kind": media_kind}
        item_count = len(detections) if detections is not None else 0
        await append_structured_trace(
            module_sdk,
            stream_id,
            method=method,
            label="engine response received",
            payload={"detections": item_count},
        )
        await append_structured_success(
            module_sdk,
            stream_id,
            method=method,
            result_label="detection results",
            result=result,
            stats=getattr(response, "stats", {}),
            extra_stats={"detections": item_count},
        )
        await update_structured_status(module_sdk, stream_id, "ok")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "success",
                    "message": module_sdk.i18n.t("system.engine.model.test.completed"),
                },
            )
        )
    except Exception as exc:
        await append_structured_error(module_sdk, stream_id, method=method, message=str(exc))
        await update_structured_status(module_sdk, stream_id, "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify("toast", {"level": "error", "message": str(exc)})
        )
