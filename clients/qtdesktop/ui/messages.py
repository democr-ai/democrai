from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class InboundMessage:
    """Normalized transport message consumed by desktop controllers."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"


class HandleInboundMessage:
    """Dispatch normalized inbound messages to desktop handlers."""

    def __init__(self, dispatcher: "MessageDispatcher") -> None:
        self.dispatcher = dispatcher

    def execute(self, message: InboundMessage) -> None:
        self.dispatcher.dispatch({"kind": message.kind, "payload": message.payload})


@dataclass(slots=True)
class UserAction:
    """User interaction command emitted by the Qt UI channel."""

    name: str
    surface_id: str
    source_component_id: str
    context: dict[str, Any] = field(default_factory=dict)


class HandleUserAction:
    """Dispatch a user action to the configured desktop action pipeline."""

    def __init__(self, dispatcher: "MessageDispatcher") -> None:
        self.dispatcher = dispatcher

    def execute(self, action: UserAction) -> None:
        self.dispatcher.dispatch({"kind": "user_action", "payload": action})


class MessageDispatcher:
    """Route incoming desktop messages to handlers by message kind."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict], None]] = {}

    def register(self, kind: str, handler: Callable[[dict], None]) -> None:
        self._handlers[kind] = handler

    def dispatch(self, message) -> None:
        kind = getattr(message, "kind", None) or message.get("kind")
        payload = getattr(message, "payload", None) or message.get("payload", {})
        handler = self._handlers.get(kind)
        if handler:
            handler(payload)
