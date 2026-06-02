from __future__ import annotations

from typing import Any

from democrai.sdk.components.base import Component


class Descriptions(Component):
    """Render key/value details from a model and a single data object."""

    type = "Descriptions"

    def __init__(
        self,
        id: str,
        model: list[dict[str, Any]] | None = None,
        data: dict[str, Any] | None = None,
        key_header: str = "Property",
        value_header: str = "Value",
        borders: bool = True,
    ):
        super().__init__(id)
        self.set_prop("model", model if model is not None else [])
        self.set_prop("data", data if data is not None else {})
        self.set_prop("key_header", key_header)
        self.set_prop("value_header", value_header)
        self.set_prop("borders", borders)
        self.allow(
            "model.set",
            "data.set",
            "key_header.set",
            "value_header.set",
            "borders.set",
        )
        self.interactive()
