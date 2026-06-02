from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout
from ....theme.tokens import theme_token

BG = theme_token("surface.window")
CARD = theme_token("surface.sidebar")
SOFT = theme_token("surface.header")
BORDER = theme_token("border.soft")
TEXT = theme_token("text.default")
MUTED = theme_token("text.muted")
ACCENT = theme_token("text.soft")


def _literal(value: Any, fallback: str = "") -> str:
    if isinstance(value, dict):
        if "literalString" in value:
            return str(value.get("literalString") or "")
        return str(value)
    if value is None:
        return fallback
    return str(value)


def _parse_qdate(value: Any) -> QDate:
    if not value:
        return QDate.currentDate()
    text = str(value).strip()
    for fmt in ("yyyy-MM-dd", "dd/MM/yyyy", "yyyy/MM/dd"):
        parsed = QDate.fromString(text, fmt)
        if parsed.isValid():
            return parsed
    return QDate.currentDate()


def _options(options: Iterable[Any]) -> list[tuple[str, Any]]:
    normalized: list[tuple[str, Any]] = []
    for option in options or []:
        if isinstance(option, dict):
            normalized.append((str(option.get("label", "")), option.get("value")))
        else:
            normalized.append((str(option), option))
    return normalized


def _collection_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value]


def _resolve_collection_index(items: list[dict[str, Any]], payload: Any) -> int | None:
    if isinstance(payload, int):
        return payload if 0 <= payload < len(items) else None
    if isinstance(payload, dict):
        if isinstance(payload.get("index"), int):
            index = int(payload["index"])
            return index if 0 <= index < len(items) else None
        target_id = payload.get("id")
        if target_id is not None:
            for index, item in enumerate(items):
                if isinstance(item, dict) and item.get("id") == target_id:
                    return index
    return None


def _clear_layout(layout: QVBoxLayout | QHBoxLayout | QGridLayout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        if child.widget() is not None:
            child.widget().setParent(None)
            child.widget().deleteLater()


def _field_shell(comp_id: str, label: str = "", max_width: int | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(comp_id)
    if max_width:
        frame.setMaximumWidth(max_width)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    if label:
        title = QLabel(label)
        title.setProperty("ui_role", "advanced_field_label")
        layout.addWidget(title)
    return frame, layout

