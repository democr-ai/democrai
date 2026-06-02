from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...base import BaseRenderer, emit_action


class StreamBindingWidget(QWidget):
    def __init__(
        self,
        *,
        props: dict[str, Any],
        app_instance: Any,
        surface_id: str,
        comp_id: str,
    ) -> None:
        super().__init__()
        self._app_instance = app_instance
        self._surface_id = surface_id
        self._comp_id = comp_id
        self._unsubscribed = False
        self.setFixedSize(QSize(0, 0))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.destroyed.connect(self._unsubscribe)
        emit_action(
            app_instance,
            "__stream_binding.subscribe",
            {
                "bindingId": comp_id,
                "stream": props.get("stream"),
                "event": props.get("event"),
                "target": props.get("target"),
                "transformer": props.get("transformer"),
            },
            surface_id,
            comp_id,
        )

    def _unsubscribe(self) -> None:
        if self._unsubscribed:
            return
        self._unsubscribed = True
        emit_action(
            self._app_instance,
            "__stream_binding.unsubscribe",
            {"bindingId": self._comp_id},
            self._surface_id,
            self._comp_id,
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._unsubscribe()
        super().closeEvent(event)


class StreamBindingRenderer(BaseRenderer):
    component_type = "StreamBinding"

    def render(
        self,
        props: dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ) -> QWidget:
        return StreamBindingWidget(
            props=props,
            app_instance=app_instance,
            surface_id=surface_id,
            comp_id=comp_id,
        )
