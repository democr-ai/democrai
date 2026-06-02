from __future__ import annotations
from typing import Any, Dict
from PySide6.QtWidgets import QWidget
from ....qss_sanitizer import qss_for_widget_style
from ...base import BaseRenderer
from .common import (
    _build_local_proxy_base_url,
    _int_value,
    _literal,
    _normalize_media_source,
    resolve_runtime_media_source,
)
from .video_player_widget import VideoPlayerWidget


class VideoRenderer(BaseRenderer):
    component_type = "Video"

    @staticmethod
    def _resolve_initial_value(
        value: Any,
        *,
        surface_id: str,
        app_instance: Any,
        default: Any = "",
    ) -> Any:
        if not isinstance(value, dict):
            return value if value is not None else default
        if "literalString" in value:
            return value.get("literalString", default)
        bindings = getattr(app_instance, "bindings", None)
        if bindings is None:
            return value.get("default", default)
        resolved = bindings.resolve_value_for_surface(value, surface_id)
        if resolved is None:
            return value.get("default", default)
        return resolved

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "source": self.PROPERTY,
            "title": self.PROPERTY,
            "autoplay": self.PROPERTY,
            "muted": self.PROPERTY,
            "loop": self.PROPERTY,
            "poster": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        title = str(
            self._resolve_initial_value(
                props.get("title"),
                surface_id=surface_id,
                app_instance=app_instance,
                default="",
            )
            or ""
        )
        source = str(
            self._resolve_initial_value(
                props.get("source"),
                surface_id=surface_id,
                app_instance=app_instance,
                default="",
            )
            or ""
        )
        poster = str(
            self._resolve_initial_value(
                props.get("poster"),
                surface_id=surface_id,
                app_instance=app_instance,
                default="",
            )
            or ""
        )
        widget = VideoPlayerWidget(
            title=title,
            width=_int_value(props.get("width"), 640),
            height=_int_value(props.get("height"), 360),
            controls=bool(props.get("controls", True)),
        )
        widget.setObjectName(comp_id)
        widget.set_autoplay(bool(props.get("autoplay", False)))
        widget.set_muted(bool(props.get("muted", False)))
        widget.set_loop(bool(props.get("loop", False)))
        widget.set_i18n(app_instance)
        setattr(widget, "_dmc_video_app_instance", app_instance)
        widget.set_poster(resolve_runtime_media_source(poster, app_instance))
        widget.set_proxy_base_url(_build_local_proxy_base_url(app_instance))
        widget.set_media_resolver(getattr(app_instance, "_media", None))
        widget.set_source(_normalize_media_source(source, app_instance))

        style = props.get("style")
        if style:
            widget.setStyleSheet(qss_for_widget_style(style, comp_id))

        return widget

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        MAP_PROP_ATTR_FN = {
            "source": [
                "set_source",
                widget.set_source,
                lambda raw: _normalize_media_source(
                    _literal(raw),
                    getattr(widget, "_dmc_video_app_instance", None),
                ),
            ],
            "title": ["set_title", widget.set_title, _literal],
            "autoplay": ["set_autoplay", widget.set_autoplay, bool],
            "muted": ["set_muted", widget.set_muted, bool],
            "loop": ["set_loop", widget.set_loop, bool],
            "poster": [
                "set_poster",
                widget.set_poster,
                lambda raw: resolve_runtime_media_source(
                    _literal(raw),
                    getattr(widget, "_dmc_video_app_instance", None),
                ),
            ],
        }

        if hasattr(widget, MAP_PROP_ATTR_FN[prop][0]):
            MAP_PROP_ATTR_FN[prop][1](MAP_PROP_ATTR_FN[prop][2](value))
            return
        """
        if prop == "source" and hasattr(widget, "set_source"):
            widget.set_source(_literal(value))
            return
        if prop == "title" and hasattr(widget, "set_title"):
            widget.set_title(_literal(value))
            return
        if prop == "autoplay" and hasattr(widget, "set_autoplay"):
            widget.set_autoplay(bool(value))
            return
        if prop == "muted" and hasattr(widget, "set_muted"):
            widget.set_muted(bool(value))
            return
        if prop == "loop" and hasattr(widget, "set_loop"):
            widget.set_loop(bool(value))
            return
        if prop == "poster" and hasattr(widget, "set_poster"):
            widget.set_poster(_literal(value))
        """
