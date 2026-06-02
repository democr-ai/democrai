from __future__ import annotations

from typing import Any

from democrai.core.application.ai.security.types import ContentIntent
from democrai.core.application.ai.security.types import ContentSecurityMetadata
from democrai.core.application.ai.security.types import ContentSourceKind
from democrai.core.application.ai.security.types import ContentTrust
from democrai.core.application.ai.security.types import SecuredContent


class PromptContextBuilder:
    def trusted_instruction(
        self,
        content: Any,
        *,
        source: ContentSourceKind = ContentSourceKind.SYSTEM,
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecuredContent:
        return self._segment(
            role="system",
            content=content,
            trust=ContentTrust.TRUSTED,
            source=source,
            intent=ContentIntent.INSTRUCTION,
            origin=origin,
            metadata=metadata,
        )

    def skill_instruction(
        self,
        content: Any,
        *,
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecuredContent:
        return self.trusted_instruction(
            content,
            source=ContentSourceKind.SKILL,
            origin=origin,
            metadata=metadata,
        )

    def user_input(
        self,
        content: Any,
        *,
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecuredContent:
        return self._segment(
            role="user",
            content=content,
            trust=ContentTrust.UNTRUSTED,
            source=ContentSourceKind.USER_INPUT,
            intent=ContentIntent.DATA,
            origin=origin,
            metadata=metadata,
        )

    def tool_output(
        self,
        content: Any,
        *,
        tool_call_id: str | None = None,
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecuredContent:
        return self._segment(
            role="tool",
            content=content,
            trust=ContentTrust.UNTRUSTED,
            source=ContentSourceKind.TOOL_OUTPUT,
            intent=ContentIntent.TOOL_RESULT,
            tool_call_id=tool_call_id,
            origin=origin,
            metadata=metadata,
        )

    def retrieval_context(
        self,
        content: Any,
        *,
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecuredContent:
        return self._segment(
            role="user",
            content=content,
            trust=ContentTrust.UNTRUSTED,
            source=ContentSourceKind.RETRIEVAL_CONTEXT,
            intent=ContentIntent.DATA,
            origin=origin,
            metadata=metadata,
        )

    def document_text(
        self,
        content: Any,
        *,
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecuredContent:
        return self._segment(
            role="user",
            content=content,
            trust=ContentTrust.UNTRUSTED,
            source=ContentSourceKind.DOCUMENT_TEXT,
            intent=ContentIntent.DATA,
            origin=origin,
            metadata=metadata,
        )

    def ocr_text(
        self,
        content: Any,
        *,
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecuredContent:
        return self._segment(
            role="user",
            content=content,
            trust=ContentTrust.UNTRUSTED,
            source=ContentSourceKind.OCR_TEXT,
            intent=ContentIntent.DATA,
            origin=origin,
            metadata=metadata,
        )

    def transcript(
        self,
        content: Any,
        *,
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecuredContent:
        return self._segment(
            role="user",
            content=content,
            trust=ContentTrust.UNTRUSTED,
            source=ContentSourceKind.TRANSCRIPT,
            intent=ContentIntent.DATA,
            origin=origin,
            metadata=metadata,
        )

    def memory(
        self,
        content: Any,
        *,
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecuredContent:
        return self._segment(
            role="user",
            content=content,
            trust=ContentTrust.UNTRUSTED,
            source=ContentSourceKind.MEMORY,
            intent=ContentIntent.DATA,
            origin=origin,
            metadata=metadata,
        )

    def model_output(
        self,
        content: Any,
        *,
        tool_calls: list[Any] | tuple[Any, ...] | None = None,
        tool_responses: list[Any] | tuple[Any, ...] | None = None,
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecuredContent:
        return self._segment(
            role="assistant",
            content=content,
            trust=ContentTrust.UNTRUSTED,
            source=ContentSourceKind.MODEL_OUTPUT,
            intent=ContentIntent.MODEL_RESPONSE,
            tool_calls=tuple(tool_calls or ()),
            tool_responses=tuple(tool_responses or ()),
            origin=origin,
            metadata=metadata,
        )

    def _segment(
        self,
        *,
        role: str,
        content: Any,
        trust: ContentTrust,
        source: ContentSourceKind,
        intent: ContentIntent,
        tool_calls: tuple[Any, ...] = (),
        tool_responses: tuple[Any, ...] = (),
        tool_call_id: str | None = None,
        origin: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecuredContent:
        return SecuredContent(
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_responses=tool_responses,
            tool_call_id=tool_call_id,
            security=ContentSecurityMetadata(
                trust=trust,
                source=source,
                intent=intent,
                origin=origin,
                metadata=metadata or {},
            ),
        )
