from typing import Dict, Any, Optional
from democrai.sdk.components.base import Component


class Image(Component):
    """Image display component for local, uploaded, or remote sources."""
    type = "Image"

    def __init__(
        self,
        id: str,
        alt: Any,
        url: Any = "",
        width: int = 45,
        height: int = 45,
        lazy: bool = False,
    ):
        super().__init__(id)

        self.set_prop("width", width)
        self.set_prop("height", height)
        self.set_prop("lazy", lazy)

        if isinstance(alt, dict) and (
            alt.get("type") in {"store", "data", "action", "literal"} or "path" in alt
        ):
            self.set_prop("alt", alt)
        elif hasattr(alt, "to_dict"):
            self.set_prop("alt", alt)
        else:
            self.set_prop("alt", {"literalString": str(alt)})

        if isinstance(url, dict) and (
            url.get("type") in {"store", "data", "action", "literal"} or "path" in url
        ):
            self.set_prop("url", url)
        elif hasattr(url, "to_dict"):
            self.set_prop("url", url)
        else:
            self.set_prop("url", {"literalString": str(url)})
