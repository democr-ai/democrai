from __future__ import annotations

from typing import Any

from democrai.core.application.ai.engine.schemas.completion import ContentPart
from democrai.core.application.ai.engine.schemas.completion import ContentType
from democrai.core.application.ai.engine.schemas.completion import Message
from democrai.core.application.ai.engine.schemas.completion import MessageRole
from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.application.ai.security.prompt.builder import PromptContextBuilder
from democrai.core.application.ai.security.types import ContentIntent
from democrai.core.application.ai.security.types import ContentSecurityMetadata
from democrai.core.application.ai.security.types import ContentSourceKind
from democrai.core.application.ai.security.types import ContentTrust
from democrai.core.application.ai.security.types import SecuredContent


_UNTRUSTED_TEXT_PREFIX = '<untrusted-content source="{source}" intent="{intent}">\n'
_UNTRUSTED_TEXT_SUFFIX = "\n</untrusted-content>"


def secured_content_to_messages(segments: list[SecuredContent]) -> list[Message]:
    return [secured_content_to_message(segment) for segment in segments]


def secured_content_to_message(segment: SecuredContent) -> Message:
    role = MessageRole(segment.role)
    return Message(
        role=role,
        content=_message_content(segment),
        tool_calls=list(segment.tool_calls) or None,
        tool_responses=list(segment.tool_responses) or None,
        tool_call_id=segment.tool_call_id,
        security=segment.security.to_dict(),
    )


def legacy_message_to_secured(value: Any) -> SecuredContent:
    message = value if isinstance(value, Message) else Message(**value)
    role = MessageRole(message.role)
    metadata = _message_security_metadata(message)
    if metadata is not None:
        pass
    elif role is MessageRole.SYSTEM:
        metadata = ContentSecurityMetadata(
            trust=ContentTrust.TRUSTED,
            source=ContentSourceKind.LEGACY,
            intent=ContentIntent.INSTRUCTION,
        )
    elif role is MessageRole.TOOL:
        metadata = ContentSecurityMetadata(
            trust=ContentTrust.UNTRUSTED,
            source=ContentSourceKind.TOOL_OUTPUT,
            intent=ContentIntent.TOOL_RESULT,
        )
    elif role is MessageRole.ASSISTANT:
        metadata = ContentSecurityMetadata(
            trust=ContentTrust.UNTRUSTED,
            source=ContentSourceKind.MODEL_OUTPUT,
            intent=ContentIntent.MODEL_RESPONSE,
        )
    else:
        metadata = ContentSecurityMetadata(
            trust=ContentTrust.UNTRUSTED,
            source=ContentSourceKind.LEGACY,
            intent=ContentIntent.DATA,
        )
    return SecuredContent(
        role=role.value,
        content=message.content,
        security=metadata,
        tool_calls=tuple(message.tool_calls or ()),
        tool_responses=tuple(message.tool_responses or ()),
        tool_call_id=message.tool_call_id,
    )


def normalize_prompt_messages(values: list[Any]) -> list[Message]:
    return secured_content_to_messages(normalize_prompt_content(values))


async def normalize_prompt_messages_with_audit(
    values: list[Any],
    *,
    stage: str,
) -> list[Message]:
    secured = normalize_prompt_content(values)
    async with ai_pipeline_step(
        type="security.filter",
        name="prompt_messages",
        input={
            "messages": len(values),
            "stage": stage.strip(),
        },
        metadata=_security_audit_metadata(secured),
    ) as step:
        messages = secured_content_to_messages(secured)
        if isinstance(step, dict):
            step["output"] = {"messages": len(messages)}
            step["stats"] = _security_audit_stats(secured, messages)
    return messages


def normalize_prompt_content(values: list[Any]) -> list[SecuredContent]:
    secured: list[SecuredContent] = []
    for value in values:
        if isinstance(value, SecuredContent):
            secured.append(value)
        else:
            secured.append(legacy_message_to_secured(value))
    return secured


def prompt_builder() -> PromptContextBuilder:
    return PromptContextBuilder()


def _message_content(segment: SecuredContent) -> Any:
    if segment.is_trusted:
        return segment.content
    content = segment.content
    if content is None:
        return _wrap_untrusted_text("", segment)
    if isinstance(content, str):
        return _wrap_untrusted_text(content, segment)
    if isinstance(content, list):
        return [
            _wrap_untrusted_part(part, segment)
            if isinstance(part, ContentPart)
            else part
            for part in content
        ]
    return _wrap_untrusted_text(str(content), segment)


def _wrap_untrusted_part(part: ContentPart, segment: SecuredContent) -> ContentPart:
    if part.type is not ContentType.TEXT:
        return part
    return part.model_copy(
        update={"text": _wrap_untrusted_text(str(part.text or ""), segment)}
    )


def _wrap_untrusted_text(text: str, segment: SecuredContent) -> str:
    stripped = str(text or "")
    if _is_wrapped_untrusted_text(stripped):
        return stripped
    return (
        _UNTRUSTED_TEXT_PREFIX.format(
            source=segment.security.source.value,
            intent=segment.security.intent.value,
        )
        + stripped
        + _UNTRUSTED_TEXT_SUFFIX
    )


def _is_wrapped_untrusted_text(text: str) -> bool:
    stripped = str(text or "").strip()
    return stripped.startswith("<untrusted-content ") and stripped.endswith(
        "</untrusted-content>"
    )


def _message_security_metadata(message: Message) -> ContentSecurityMetadata | None:
    payload = message.security
    if not isinstance(payload, dict):
        return None
    try:
        return ContentSecurityMetadata(
            trust=ContentTrust(payload.get("trust")),
            source=ContentSourceKind(payload.get("source")),
            intent=ContentIntent(payload.get("intent")),
            origin=(
                str(payload.get("origin") or "").strip()
                if payload.get("origin")
                else None
            ),
            metadata=(
                dict(payload.get("metadata") or {})
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        )
    except Exception:
        return None


def _security_audit_metadata(secured: list[SecuredContent]) -> dict[str, Any]:
    return {
        "policy": "beta_role_based",
        "sources": sorted({segment.security.source.value for segment in secured}),
        "intents": sorted({segment.security.intent.value for segment in secured}),
    }


def _security_audit_stats(
    secured: list[SecuredContent],
    messages: list[Message],
) -> dict[str, Any]:
    wrapped = 0
    for message in messages:
        content = message.content
        if isinstance(content, str) and _is_wrapped_untrusted_text(content):
            wrapped += 1
            continue
        if isinstance(content, list):
            for part in content:
                if (
                    isinstance(part, ContentPart)
                    and isinstance(part.text, str)
                    and _is_wrapped_untrusted_text(part.text)
                ):
                    wrapped += 1
                    break
    return {
        "trusted": sum(1 for segment in secured if segment.is_trusted),
        "untrusted": sum(1 for segment in secured if not segment.is_trusted),
        "wrapped": wrapped,
        "legacy": sum(
            1
            for segment in secured
            if segment.security.source is ContentSourceKind.LEGACY
        ),
        "system_trusted_by_role": sum(
            1
            for segment in secured
            if segment.role == MessageRole.SYSTEM.value and segment.is_trusted
        ),
        "tool_outputs": sum(
            1
            for segment in secured
            if segment.security.source is ContentSourceKind.TOOL_OUTPUT
        ),
    }
