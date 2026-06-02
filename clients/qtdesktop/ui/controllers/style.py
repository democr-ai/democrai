from __future__ import annotations

import json
import os
from typing import Any

from PySide6.QtWidgets import QApplication

from ...logging import get_logger
from ..theme.tokens import set_application_theme
from ...utils.resources import get_resource_path
from ...utils.stylesheet import load_stylesheet_from_paths


class StyleController:
    """Runtime stylesheet loading and hot-reload behavior."""

    def __init__(self, window: Any, debug_enabled: bool) -> None:
        """Bind to window transport and debug configuration."""
        self.window = window
        self.debug_enabled = debug_enabled

    def apply_runtime_stylesheet(self) -> None:
        """Load `.less/.css` and apply stylesheet to current QApplication."""
        store = getattr(self.window, "store", None)
        theme = "dark"
        if store is not None:
            theme = str(store.get("/system/client/theme", "dark", "global") or "dark")
        normalized_theme = set_application_theme(theme)
        css = load_app_stylesheet(self.debug_enabled, theme=normalized_theme)
        if css:
            instance = QApplication.instance()
            if instance:
                instance.setStyleSheet(css)  # type: ignore

    def handle_hot_reload(self) -> None:
        """Reload styles and re-send `init` to refresh UI state bindings."""
        self.window._debug("Hot reload signal received, refreshing UI")
        try:
            self.apply_runtime_stylesheet()
            self.window._debug("Stylesheet reloaded")
        except Exception as e:
            self.window._warn(f"Failed to reload stylesheet: {e}")

        session = getattr(self.window, "_session", None)
        if session is not None:
            session.refresh_current_view(clear_page_scope=True)
            return

        msg = {"type": "init", "jwt": self.window.jwt}
        raw = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
        self.window.client.write(raw)
        self.window.client.flush()


def _theme_assets(theme: str) -> tuple[str, str]:
    normalized_theme = str(theme or "dark").strip().lower()
    if normalized_theme == "light":
        return (
            get_resource_path(os.path.join("assets", "style_light.less")),
            get_resource_path(os.path.join("assets", "style_light.css")),
        )
    return (
        get_resource_path(os.path.join("assets", "style_dark.less")),
        get_resource_path(os.path.join("assets", "style_dark.css")),
    )


def load_app_stylesheet(debug_enabled: bool, *, theme: str = "dark") -> str:
    """Compile/load application stylesheet using explicit dark/light entrypoints."""
    less_path, css_path = _theme_assets(theme)
    css = load_stylesheet_from_paths(
        less_path=less_path,
        css_path=css_path,
        logger=get_logger(),
        debug=debug_enabled,
    )
    if css:
        return css

    # Legacy fallback when themed assets are missing.
    return load_stylesheet_from_paths(
        less_path=get_resource_path(os.path.join("assets", "style.less")),
        css_path=get_resource_path(os.path.join("assets", "style.css")),
        logger=get_logger(),
        debug=debug_enabled,
    )
