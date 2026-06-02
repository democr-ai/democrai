from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class ContentTrust(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class ContentSourceKind(str, Enum):
    SYSTEM = "system"
    USER_INPUT = "user_input"
    TOOL_OUTPUT = "tool_output"
    RETRIEVAL_CONTEXT = "retrieval_context"
    MEMORY = "memory"
    SKILL = "skill"
    MODEL_OUTPUT = "model_output"
    DOCUMENT_TEXT = "document_text"
    OCR_TEXT = "ocr_text"
    TRANSCRIPT = "transcript"
    LEGACY = "legacy"


class ContentIntent(str, Enum):
    INSTRUCTION = "instruction"
    DATA = "data"
    TOOL_RESULT = "tool_result"
    MODEL_RESPONSE = "model_response"


@dataclass(frozen=True)
class ContentSecurityMetadata:
    trust: ContentTrust
    source: ContentSourceKind
    intent: ContentIntent
    origin: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "trust", ContentTrust(self.trust))
        object.__setattr__(self, "source", ContentSourceKind(self.source))
        object.__setattr__(self, "intent", ContentIntent(self.intent))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trust": self.trust.value,
            "source": self.source.value,
            "intent": self.intent.value,
        }
        if self.origin:
            payload["origin"] = self.origin
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class SecuredContent:
    role: str
    content: Any
    security: ContentSecurityMetadata
    tool_calls: tuple[Any, ...] = ()
    tool_responses: tuple[Any, ...] = ()
    tool_call_id: str | None = None

    @property
    def is_trusted(self) -> bool:
        return self.security.trust is ContentTrust.TRUSTED

    @property
    def is_instruction(self) -> bool:
        return self.security.intent is ContentIntent.INSTRUCTION
