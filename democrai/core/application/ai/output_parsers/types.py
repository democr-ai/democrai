from __future__ import annotations

from dataclasses import dataclass, field

from democrai.core.application.ai.engine.schemas.completion import ToolCall


@dataclass(frozen=True)
class ParsedModelOutput:
    content: str | None = None
    reasoning: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class StreamParseState:
    buffer: str = ""
