from __future__ import annotations

import time
from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action
from democrai.sdk.engines import KGExtractionOptions

from modules.system.actions.engine.model_tests.common import get_provider, load_context
from modules.system.actions.engine.model_tests.extract_triples_result import (
    append_extract_triples_error,
    append_extract_triples_success,
    append_extract_triples_trace,
    clear_extract_triples_result,
    update_extract_triples_status,
)
from modules.system.utils.actions.engine.model_test_support import (
    _number_value,
    _optional_int_value,
    _runtime_field_names,
)


@action("test_engine_model_extract_triples")
@permission_required(["system.engine.model.manage"])
async def test_engine_model_extract_triples(ctx: dict[str, Any], module_sdk):
    stream_id = str(ctx.get("stream_id") or "")
    test_ctx = load_context(ctx, module_sdk, require_prompt=False)
    if test_ctx is None:
        return module_sdk.effects.respond(module_sdk.effects.render())
    if not stream_id:
        raise RuntimeError("stream_id_required")

    await clear_extract_triples_result(module_sdk, stream_id)
    try:
        content = str(test_ctx.payload.get("content") or "").strip()
        if not content:
            raise ValueError("content_required")
        options = _extract_triples_options(test_ctx)
        await append_extract_triples_trace(
            module_sdk,
            stream_id,
            label="extract triples request",
            payload={
                "model_row_id": test_ctx.row_id,
                "kind": _kind(test_ctx),
                "content_chars": len(content),
                "options": options.model_dump(),
            },
        )
        provider, warmup_ms, provider_error = await get_provider(
            module_sdk,
            test_ctx.row_id,
        )
        if provider is None:
            await append_extract_triples_error(
                module_sdk,
                stream_id,
                message=provider_error,
            )
            await update_extract_triples_status(module_sdk, stream_id, "error")
            return module_sdk.effects.respond(
                module_sdk.effects.notify(
                    "toast",
                    {"level": "error", "message": provider_error},
                )
            )
        await append_extract_triples_trace(
            module_sdk,
            stream_id,
            label="provider ready",
            payload={"warmup_ms": warmup_ms},
        )
        await append_extract_triples_trace(
            module_sdk,
            stream_id,
            label="engine call started",
            payload={"method": "extract_triples"},
        )
        started = time.perf_counter()
        graph = await provider.extract_triples(
            kind=_kind(test_ctx),
            title=_optional_text(test_ctx, "title"),
            summary=_optional_text(test_ctx, "summary"),
            content=content,
            options=options,
        )
        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        graph_payload = _graph_payload(graph)
        await append_extract_triples_trace(
            module_sdk,
            stream_id,
            label="engine response received",
            payload={
                "entities": len(list(graph_payload.get("entities") or [])),
                "relations": len(list(graph_payload.get("relations") or [])),
            },
        )
        await append_extract_triples_success(
            module_sdk,
            stream_id,
            graph=graph_payload,
            stats=getattr(graph, "stats", {}),
        )
        await update_extract_triples_status(module_sdk, stream_id, "ok")
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
        await append_extract_triples_error(module_sdk, stream_id, message=str(exc))
        await update_extract_triples_status(module_sdk, stream_id, "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {"level": "error", "message": str(exc)},
            )
        )


def _kind(test_ctx) -> str:
    return str(test_ctx.payload.get("kind") or "document").strip() or "document"


def _optional_text(test_ctx, key: str) -> str | None:
    value = str(test_ctx.payload.get(key) or "").strip()
    return value or None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    return [
        item.strip()
        for item in str(value or "").splitlines()
        if item.strip()
    ]


def _runtime_value(test_ctx, name: str) -> Any:
    if test_ctx.payload.get(name) not in (None, ""):
        return test_ctx.payload.get(name)
    return test_ctx.runtime.get(name)


def _extract_triples_options(test_ctx) -> KGExtractionOptions:
    defaults = KGExtractionOptions()
    threshold = _runtime_value(test_ctx, "threshold")
    extra: dict[str, Any] = {}
    for name in _runtime_field_names(test_ctx.extra_config.get("options_schema")):
        if name in KGExtractionOptions.model_fields:
            continue
        value = _runtime_value(test_ctx, name)
        if value not in (None, ""):
            extra[name] = value
    return KGExtractionOptions(
        max_entities=_optional_int_value(_runtime_value(test_ctx, "max_entities"))
        or defaults.max_entities,
        max_relations=_optional_int_value(_runtime_value(test_ctx, "max_relations"))
        or defaults.max_relations,
        temperature=_number_value(
            _runtime_value(test_ctx, "temperature"),
            defaults.temperature,
        ),
        max_tokens=_optional_int_value(_runtime_value(test_ctx, "max_tokens")),
        entity_labels=_string_list(_runtime_value(test_ctx, "entity_labels")),
        relation_labels=_string_list(_runtime_value(test_ctx, "relation_labels")),
        threshold=(
            None
            if threshold in (None, "")
            else _number_value(threshold, defaults.threshold)
        ),
        top_k=_optional_int_value(_runtime_value(test_ctx, "top_k")),
        extra=extra,
    )


def _graph_payload(graph: Any) -> dict[str, Any]:
    if hasattr(graph, "model_dump"):
        return dict(graph.model_dump(mode="python"))
    if isinstance(graph, dict):
        return dict(graph)
    return {"entities": [], "relations": []}
