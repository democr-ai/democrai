from typing import Dict, Any, Optional
from democrai.sdk.components.base import Component

class Audio(Component):
    """Audio playback component for local or remote media sources."""
    type = "Audio"

    def __init__(
        self,
        id: str,
        source: str = "",
        title: str = "",
        autoplay: bool = False,
        muted: bool = False,
        loop: bool = False,
        controls: bool = True,
        poster: str = "",
        width: int = 640,
        height: int = 180,
    ):
        super().__init__(id)
        if isinstance(source, dict) and (
            source.get("type") in {"store", "data", "action", "literal"}
            or "path" in source
        ):
            self.set_prop("source", source)
        elif hasattr(source, "to_dict"):
            self.set_prop("source", source)
        else:
            self.set_prop("source", {"literalString": str(source)})

        if isinstance(title, dict) and (
            title.get("type") in {"store", "data", "action", "literal"}
            or "path" in title
        ):
            self.set_prop("title", title)
        elif hasattr(title, "to_dict"):
            self.set_prop("title", title)
        else:
            self.set_prop("title", {"literalString": str(title)})

        self.set_prop("autoplay", autoplay)
        self.set_prop("muted", muted)
        self.set_prop("loop", loop)
        self.set_prop("controls", controls)
        if isinstance(poster, dict) and (
            poster.get("type") in {"store", "data", "action", "literal"}
            or "path" in poster
        ):
            self.set_prop("poster", poster)
        elif hasattr(poster, "to_dict"):
            self.set_prop("poster", poster)
        else:
            self.set_prop("poster", {"literalString": str(poster)})
        self.set_prop("width", width)
        self.set_prop("height", height)
