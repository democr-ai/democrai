from __future__ import annotations

from typing import Any

from democrai.core.application.ai.engine.schemas.completion import MessageRole
from democrai.core.application.ai.pipeline_context import AIPipelineContext
from democrai.core.application.knowledge.models import KnowledgeIngestItem
from democrai.core.application.knowledge.models import KnowledgeSourceInput
from democrai.core.application.knowledge.repository import KnowledgeRepository
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import req_ctx


def _knowledge_repository() -> KnowledgeRepository:
    ctx = app_ctx()
    service = getattr(ctx, "knowledge_service", None)
    repository = getattr(service, "repository", None)
    if repository is not None:
        return repository
    db = getattr(ctx, "db", None)
    if db is None:
        raise RuntimeError("knowledge_repository_unavailable")
    return KnowledgeRepository(db.get_session)


def ingest_ai_completion_call(
    *,
    context: AIPipelineContext,
    method: str,
    messages: Any,
    response: Any = None,
    stream_chunks: list[Any] | None = None,
    ingest_meta: dict[str, Any] | None = None,
) -> None:
    user_id = _context_user_id(context)
    if user_id is None:
        raise RuntimeError("knowledge_ai_capture_user_required")
    metadata = _capture_metadata(
        context=context,
        method=method,
        ingest_meta=ingest_meta,
    )
    items = _message_items(messages, metadata=metadata)
    output = _response_text(response=response, stream_chunks=stream_chunks)
    if output:
        items.append(
            KnowledgeIngestItem(
                kind="agent_message",
                item_id=f"{context.current_pipeline_id}:response",
                title="Assistant response",
                content=output,
                metadata={
                    **metadata,
                    "role": MessageRole.ASSISTANT.value,
                    "message_direction": "output",
                },
            )
        )
    if not items:
        return
    _knowledge_repository().enqueue_ingestion_request(
        user_id=user_id,
        organization_id=_context_organization_id(context),
        source=KnowledgeSourceInput(
            source_type="ai_engine_call",
            source_id=context.pipeline_id,
            title=f"AI {method}",
            metadata=metadata,
        ),
        items=tuple(items),
        origin_type="ai_capture",
    )


def _capture_metadata(
    *,
    context: AIPipelineContext,
    method: str,
    ingest_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    metadata = dict(context.metadata or {})
    metadata.update(dict(ingest_meta or {}))
    metadata.update(
        {
            "source_type": "ai_engine_call",
            "pipeline_id": context.pipeline_id,
            "current_pipeline_id": context.current_pipeline_id,
            "parent_pipeline_id": context.parent_pipeline_id,
            "request_id": context.request_id,
            "root_method": context.root_method,
            "method": method,
            "provider": context.provider,
            "engine": context.engine,
            "engine_row_id": context.engine_row_id,
            "model_registry_id": context.model_registry_id,
            "model_name": context.model_name,
            "caller_module": context.caller_module,
        }
    )
    return {key: value for key, value in metadata.items() if value is not None}


def _message_items(messages: Any, *, metadata: dict[str, Any]) -> list[KnowledgeIngestItem]:
    items: list[KnowledgeIngestItem] = []
    if not isinstance(messages, list):
        return items
    for index, message in enumerate(messages):
        role = _message_role(message)
        if not role or role == MessageRole.SYSTEM.value:
            continue
        content = _message_text(message)
        if not content:
            continue
        items.append(
            KnowledgeIngestItem(
                kind="agent_message",
                item_id=f"{metadata['current_pipeline_id']}:message:{index}",
                title=f"{role} message",
                content=content,
                metadata={
                    **metadata,
                    "role": role,
                    "message_direction": "input",
                    "message_index": index,
                },
            )
        )
    return items


def _message_role(message: Any) -> str:
    role = getattr(message, "role", None)
    if isinstance(message, dict):
        role = message.get("role")
    value = getattr(role, "value", role)
    return str(value or "").strip().lower()


def _message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(message, dict):
        content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        text = getattr(part, "text", None)
        if isinstance(part, dict):
            text = part.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n".join(parts).strip()


def _response_text(*, response: Any = None, stream_chunks: list[Any] | None = None) -> str:
    if stream_chunks is not None:
        return "".join(
            str(getattr(chunk, "delta", "") or "")
            for chunk in stream_chunks
            if getattr(chunk, "delta", None)
        ).strip()
    content = getattr(response, "content", None)
    return str(content or "").strip()


def _context_user_id(context: AIPipelineContext) -> int | None:
    if context.user_id is not None:
        return context.user_id
    try:
        return req_ctx().user
    except Exception:
        return None


def _context_organization_id(context: AIPipelineContext) -> int | None:
    organization_id = to_optional_int(context.organization_id)
    if organization_id is not None:
        return organization_id
    try:
        return to_optional_int(getattr(req_ctx(), "organization_id", None))
    except Exception:
        return None
