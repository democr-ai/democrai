from __future__ import annotations

from democrai.sdk.components.base import Component


class AttachmentPreview(Component):
    """Inline attachment preview component for chat/overlay surfaces."""

    type = "AttachmentPreview"

    def __init__(
        self,
        id: str,
        *,
        name: str = "",
        mime_type: str = "",
        storage_path: str = "",
        file_id: str = "",
        url: str = "",
        height: int = 420,
    ):
        super().__init__(id)
        self.set_prop("name", name)
        self.set_prop("mime_type", mime_type)
        self.set_prop("storage_path", storage_path)
        self.set_prop("file_id", file_id)
        self.set_prop("url", url)
        self.set_prop("height", height)
