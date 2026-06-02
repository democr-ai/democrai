from __future__ import annotations

from typing import Dict, Optional

from .models import ChannelDefinition


class ChannelRegistry:
    def __init__(self) -> None:
        self._channels: Dict[str, ChannelDefinition] = {}

    def register(self, definition: ChannelDefinition) -> None:
        self._channels[str(definition.id)] = definition

    def get(self, channel_id: str) -> Optional[ChannelDefinition]:
        return self._channels.get(channel_id if isinstance(channel_id, str) else "")

    def get_all(self, *, module_name: str | None = None) -> list[ChannelDefinition]:
        values = list(self._channels.values())
        if module_name is None:
            return values
        return [item for item in values if item.module_name == module_name]


channel_registry = ChannelRegistry()
