from __future__ import annotations

import os
import re
from typing import Any

from PySide6.QtWidgets import QApplication

_APP_THEME_PROPERTY = "democrai_client_theme"
_VALID_THEMES = {"dark", "light"}

_THEME_TOKENS: dict[str, dict[str, str]] = {
    "dark": {
        "surface.window": "#0A0A0A",
        "surface.main": "#000000",
        "surface.sidebar": "#171717",
        "surface.header": "#171717",
        "surface.drawer": "#0A0A0A",
        "border.sidebar": "#3f3f46",
        "border.drawer": "#27272a",
        "border.soft": "#334155",
        "border.hover": "#64748b",
        "text.primary": "#FAFAFA",
        "text.default": "#E4E4E7",
        "text.muted": "#A1A1AA",
        "text.soft": "#E5E5E5",
        "text.inverse": "#09090B",
        "text.drawer_close": "#94A3B8",
        "text.drawer_close_hover": "#F1F5F9",
        "color.danger": "#EF4444",
        "color.success": "#22C55E",
        "color.warning": "#F59E0B",
        "color.info": "#0B4EA2",
        "icon.default": "#94A3B8",
        "icon.sidebar.active": "#FAFAFA",
        "icon.sidebar.idle": "#A1A1AA",
        "icon.sidebar.menu": "#E4E4E7",
        "badge.notification.bg": "#ef4444",
        "badge.notification.text": "#ffffff",
        "data.surface.base": "#1C2433",
        "data.surface.panel": "#142036",
        "data.surface.panel_alt": "#182841",
        "data.surface.row.even": "#16253C",
        "data.surface.row.odd": "#1A2B45",
        "data.border.grid": "#2A3F5A",
        "data.border.soft": "#33506F",
        "data.text.primary": "#E2E8F0",
        "data.text.muted": "#94A3B8",
        "data.text.subtle": "#8FA4BF",
        "data.accent": "#60A5FA",
        "data.accent.alt": "#38BDF8",
        "data.status.planned": "#60A5FA",
        "data.status.active": "#38BDF8",
        "data.status.blocked": "#F59E0B",
        "data.status.done": "#34D399",
        "data.status.risk": "#FB7185",
        "workflow.node.fill": "#1F2937",
        "workflow.node.stroke": "#60A5FA",
        "workflow.node.text": "#E2E8F0",
        "diagram.node.fill": "#162033",
        "diagram.node.stroke": "#7DD3FC",
        "diagram.node.text": "#E2E8F0",
        "calendar.bg": "#0F172A",
        "calendar.border": "#1E293B",
        "calendar.selection.bg": "#172A46",
        "calendar.selection.border": "#3B82F6",
        "calendar.slot.selection": "#1E3A5F",
        "calendar.outside": "#060A10",
        "calendar.actionbar.bg": "#1E293B",
        "calendar.actionbar.border": "#334155",
        "calendar.text.title": "#E2E8F0",
        "calendar.text.sub": "#475569",
        "calendar.text.nav": "#94A3B8",
        "calendar.text.header": "#64748B",
        "calendar.text.time": "#475569",
        "calendar.accent": "#3B82F6",
    },
    "light": {
        "surface.window": "#F8FAFC",
        "surface.main": "#FFFFFF",
        "surface.sidebar": "#F8FAFC",
        "surface.header": "#F1F5F9",
        "surface.drawer": "#FFFFFF",
        "border.sidebar": "#E2E8F0",
        "border.drawer": "#CBD5E1",
        "border.soft": "#CBD5E1",
        "border.hover": "#94A3B8",
        "text.primary": "#0F172A",
        "text.default": "#0F172A",
        "text.muted": "#64748B",
        "text.soft": "#334155",
        "text.inverse": "#0F172A",
        "text.drawer_close": "#334155",
        "text.drawer_close_hover": "#0F172A",
        "color.danger": "#DC2626",
        "color.success": "#16A34A",
        "color.warning": "#D97706",
        "color.info": "#0B4EA2",
        "icon.default": "#64748B",
        "icon.sidebar.active": "#FFFFFF",
        "icon.sidebar.idle": "#FFFFFF",
        "icon.sidebar.menu": "#FFFFFF",
        "badge.notification.bg": "#DC2626",
        "badge.notification.text": "#ffffff",
        "data.surface.base": "#F8FAFC",
        "data.surface.panel": "#FFFFFF",
        "data.surface.panel_alt": "#F1F5F9",
        "data.surface.row.even": "#F8FAFC",
        "data.surface.row.odd": "#F1F5F9",
        "data.border.grid": "#CBD5E1",
        "data.border.soft": "#E2E8F0",
        "data.text.primary": "#0F172A",
        "data.text.muted": "#64748B",
        "data.text.subtle": "#475569",
        "data.accent": "#2563EB",
        "data.accent.alt": "#0284C7",
        "data.status.planned": "#2563EB",
        "data.status.active": "#0284C7",
        "data.status.blocked": "#D97706",
        "data.status.done": "#16A34A",
        "data.status.risk": "#DC2626",
        "workflow.node.fill": "#EEF2FF",
        "workflow.node.stroke": "#2563EB",
        "workflow.node.text": "#0F172A",
        "diagram.node.fill": "#EFF6FF",
        "diagram.node.stroke": "#0284C7",
        "diagram.node.text": "#0F172A",
        "calendar.bg": "#FFFFFF",
        "calendar.border": "#CBD5E1",
        "calendar.selection.bg": "#EFF6FF",
        "calendar.selection.border": "#60A5FA",
        "calendar.slot.selection": "#F0F9FF",
        "calendar.outside": "#F1F5F9",
        "calendar.actionbar.bg": "#F8FAFC",
        "calendar.actionbar.border": "#CBD5E1",
        "calendar.text.title": "#0F172A",
        "calendar.text.sub": "#64748B",
        "calendar.text.nav": "#64748B",
        "calendar.text.header": "#475569",
        "calendar.text.time": "#64748B",
        "calendar.accent": "#3B82F6",
    },
}

_LESS_TOKEN_PATTERN = re.compile(
    r"@(?P<name>token__[A-Za-z0-9_]+)\s*:\s*(?P<value>[^;]+);"
)
_LESS_THEME_TOKEN_FILES = {
    "dark": os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "assets",
            "style_sections",
            "theme_tokens_dark.less",
        )
    ),
    "light": os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "assets",
            "style_sections",
            "theme_tokens_light.less",
        )
    ),
}


def _parse_less_runtime_tokens(path: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    if not os.path.exists(path):
        return parsed
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    for match in _LESS_TOKEN_PATTERN.finditer(source):
        raw_name = match.group("name")
        raw_value = match.group("value").strip()
        token_name = raw_name.removeprefix("token__").replace("__", ".")
        if token_name:
            parsed[token_name] = raw_value
    return parsed


def _load_theme_tokens_from_less() -> dict[str, dict[str, str]]:
    loaded: dict[str, dict[str, str]] = {}
    for theme, path in _LESS_THEME_TOKEN_FILES.items():
        loaded[theme] = _parse_less_runtime_tokens(path)
    return loaded


_LESS_THEME_TOKENS = _load_theme_tokens_from_less()
for _theme_name, _theme_values in _LESS_THEME_TOKENS.items():
    if _theme_values:
        base = _THEME_TOKENS.get(_theme_name, {}).copy()
        base.update(_theme_values)
        _THEME_TOKENS[_theme_name] = base


def normalize_theme(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return value if value in _VALID_THEMES else "dark"


def set_application_theme(theme: Any) -> str:
    normalized = normalize_theme(theme)
    app = QApplication.instance()
    if app is not None:
        app.setProperty(_APP_THEME_PROPERTY, normalized)
    return normalized


def current_theme(*, app_instance: Any | None = None) -> str:
    if app_instance is not None:
        store = getattr(app_instance, "store", None)
        if store is not None:
            try:
                return normalize_theme(store.get("/system/client/theme", "dark", "auto"))
            except Exception:
                return "dark"
    app = QApplication.instance()
    if app is None:
        return "dark"
    return normalize_theme(app.property(_APP_THEME_PROPERTY))


def theme_token(name: str, *, theme: Any | None = None, app_instance: Any | None = None) -> str:
    resolved_theme = normalize_theme(theme) if theme is not None else current_theme(app_instance=app_instance)
    tokens = _THEME_TOKENS.get(resolved_theme, _THEME_TOKENS["dark"])
    return tokens.get(name, _THEME_TOKENS["dark"].get(name, ""))


def themed_status_color(status: str, *, app_instance: Any | None = None, fallback: str = "") -> str:
    key = str(status or "").strip().lower()
    mapping = {
        "planned": "data.status.planned",
        "active": "data.status.active",
        "running": "data.status.active",
        "blocked": "data.status.blocked",
        "warning": "data.status.blocked",
        "done": "data.status.done",
        "success": "data.status.done",
        "risk": "data.status.risk",
        "error": "data.status.risk",
    }
    token_name = mapping.get(key)
    if token_name:
        return theme_token(token_name, app_instance=app_instance)
    return fallback or theme_token("data.accent", app_instance=app_instance)


def calendar_theme(*, app_instance: Any | None = None) -> dict[str, str]:
    return {
        "bg": theme_token("calendar.bg", app_instance=app_instance),
        "border": theme_token("calendar.border", app_instance=app_instance),
        "sel_bg": theme_token("calendar.selection.bg", app_instance=app_instance),
        "sel_border": theme_token("calendar.selection.border", app_instance=app_instance),
        "slot_sel": theme_token("calendar.slot.selection", app_instance=app_instance),
        "outside": theme_token("calendar.outside", app_instance=app_instance),
        "abar_bg": theme_token("calendar.actionbar.bg", app_instance=app_instance),
        "abar_border": theme_token("calendar.actionbar.border", app_instance=app_instance),
        "title": theme_token("calendar.text.title", app_instance=app_instance),
        "sub": theme_token("calendar.text.sub", app_instance=app_instance),
        "nav": theme_token("calendar.text.nav", app_instance=app_instance),
        "hdr": theme_token("calendar.text.header", app_instance=app_instance),
        "time": theme_token("calendar.text.time", app_instance=app_instance),
        "blue": theme_token("calendar.accent", app_instance=app_instance),
    }


def button_icon_colors(
    variant: str,
    appearance: str,
    shape: str,
    active: bool,
    *,
    profile: str = "button",
    app_instance: Any | None = None,
) -> tuple[str, str]:
    v = str(variant or "").strip()
    a = str(appearance or "").strip()
    is_filled_primary_or_danger = a == "default" and v in {
        "primary",
        "danger",
        "destructive",
    }
    inverse = theme_token("text.inverse", app_instance=app_instance)
    on_dark = theme_token("text.primary", app_instance=app_instance)
    default_text = theme_token("text.default", app_instance=app_instance)
    muted = theme_token("text.muted", app_instance=app_instance)
    soft = theme_token("text.soft", app_instance=app_instance)
    danger = theme_token("color.danger", app_instance=app_instance)
    success = theme_token("color.success", app_instance=app_instance)
    warning = theme_token("color.warning", app_instance=app_instance)
    info = theme_token("color.info", app_instance=app_instance)

    if profile == "contrast":
        if is_filled_primary_or_danger:
            return "#FFFFFF", "#FFFFFF"
        if a == "default":
            if v in {"default", "secondary", "outline", "ghost", "link"}:
                normal, hover = inverse, inverse
            elif v == "destructive":
                normal, hover = on_dark, on_dark
            elif v == "success":
                normal, hover = "#052E16", "#052E16"
            elif v == "warning":
                normal, hover = "#111827", "#111827"
            else:
                normal, hover = inverse, inverse
        elif a in {"ghost", "outline"}:
            if v == "destructive":
                normal, hover = danger, on_dark
            elif v == "success":
                normal, hover = success, on_dark
            elif v == "warning":
                normal, hover = warning, on_dark
            else:
                normal, hover = on_dark, on_dark
        elif a == "link":
            if v == "destructive":
                normal, hover = danger, danger
            elif v in {"primary", "info"}:
                normal, hover = info, info
            else:
                normal, hover = on_dark, on_dark
        else:
            normal, hover = on_dark, on_dark

        if shape == "round" and a == "ghost" and v in {"default", "secondary"}:
            if active:
                return inverse, on_dark
            return on_dark, on_dark
        return normal, hover

    if a == "default":
        if is_filled_primary_or_danger:
            return "#FFFFFF", "#FFFFFF"
        if v == "default":
            normal, hover = default_text, default_text
        elif v in {"secondary", "outline", "ghost", "link", "primary"}:
            normal, hover = inverse, inverse
        elif v == "destructive":
            normal, hover = danger, danger
        elif v == "success":
            normal, hover = success, success
        elif v == "warning":
            normal, hover = warning, warning
        elif v in {"primary", "info"}:
            normal, hover = info, info
        else:
            normal, hover = inverse, inverse
    elif a in {"ghost", "outline"}:
        if v == "destructive":
            normal, hover = danger, danger
        elif v == "success":
            normal, hover = success, success
        elif v == "warning":
            normal, hover = warning, warning
        elif v in {"primary", "info"}:
            normal, hover = info, info
        else:
            normal, hover = muted, soft
    elif a == "link":
        if v == "destructive":
            normal, hover = danger, danger
        elif v in {"primary", "info"}:
            normal, hover = info, info
        elif v == "success":
            normal, hover = success, success
        elif v == "warning":
            normal, hover = warning, warning
        else:
            normal, hover = muted, soft
    else:
        normal, hover = on_dark, on_dark

    if shape == "round" and a == "ghost" and v in {"default", "secondary"}:
        if active:
            return inverse, on_dark
        return on_dark, on_dark
    return normal, hover
