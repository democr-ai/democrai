from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from democrai.core.platform.channels.models import Message


@dataclass
class PipelineContext:
    message: Message
    session: dict[str, Any]
    thread_id: str | None = None

    resolved_tools: list[Any] = field(default_factory=list)
    extra_system_prompts: list[str] = field(default_factory=list)
    memory_chunks: list[dict[str, Any]] = field(default_factory=list)

    ingested_content: str | None = None
    intent: str | None = None
    model_selected: str | None = None
    response_text: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)
