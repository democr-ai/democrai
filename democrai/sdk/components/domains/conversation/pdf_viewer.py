from __future__ import annotations

from democrai.sdk.components.base import Component


class PdfViewer(Component):
    """Dedicated PDF viewer component with toolbar controls."""

    type = "PdfViewer"

    def __init__(
        self,
        id: str,
        *,
        name: str = "",
        storage_path: str = "",
        file_id: str = "",
        url: str = "",
        height: int = 520,
        fit: str = "",
    ):
        super().__init__(id)
        self.set_prop("name", name)
        self.set_prop("storage_path", storage_path)
        self.set_prop("file_id", file_id)
        self.set_prop("url", url)
        self.set_prop("height", height)
        self.set_prop("fit", fit)
