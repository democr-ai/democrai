from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class Attachment:
    filename: str
    mime_type: str
    content: bytes
    size: int = 0
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    text: str | None = None
    audio: bytes | None = None
    attachments: list[Attachment] = field(default_factory=list)

    sender: str = ""
    channel_id: str = ""
    source_ref: str | None = None
    thread_id: str | None = None
    reply_to: Any = None

    intent: str | None = None
    ingested_content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelDefinition:
    id: str
    name: str
    description: str = ""
    module_name: str = "core"

    receive: Callable[[Any], Awaitable[Message]] | None = None
    send: Callable[[Message, Any], Awaitable[None]] | None = None

    supports_audio_input: bool = False
    supports_audio_output: bool = False
    supports_attachments: bool = False
    supports_threads: bool = False
    webhook_path: str | None = None

    config_schema: dict[str, Any] | None = None
    config_version: int = 1
