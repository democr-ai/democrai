from __future__ import annotations

from typing import Any

from democrai.sdk.components.base import Component


class StreamBinding(Component):
    """Invisible component that binds runtime stream events to client state."""

    type = "StreamBinding"

    def __init__(
        self,
        id: str,
        stream: str,
        event: str = "",
        target: dict[str, Any] | None = None,
        transformer: str | dict[str, Any] | None = None,
    ):
        super().__init__(id)
        self.set_prop("stream", stream)
        if event:
            self.set_prop("event", event)
        self.set_prop("target", target if target is not None else {})
        if transformer:
            self.set_prop("transformer", transformer)
