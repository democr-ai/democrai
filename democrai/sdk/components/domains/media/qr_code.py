from typing import Optional

from democrai.sdk.components.base import Component


class QRCode(Component):
    """QR code component generated from a textual payload."""
    type = "QRCode"

    def __init__(
        self,
        id: str,
        content: str,
        *,
        size: int = 220,
        border: int = 4,
        fill_color: str = "#111111",
        back_color: str = "#ffffff",
    ):
        super().__init__(id)
        if isinstance(content, dict) and (
            content.get("type") in {"store", "data", "action", "literal"}
            or "path" in content
        ):
            self.set_prop("content", content)
        elif hasattr(content, "to_dict"):
            self.set_prop("content", content)
        else:
            self.set_prop("content", {"literalString": str(content)})
        self.set_prop("size", int(size))
        self.set_prop("border", int(border))
        self.set_prop("fill_color", str(fill_color))
        self.set_prop("back_color", str(back_color))
