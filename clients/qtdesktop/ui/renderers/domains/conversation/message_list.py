from __future__ import annotations
import json
import html
import math
import mimetypes
import os
import tempfile
import time
import shiboken6
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlencode
from PySide6.QtCore import Qt, QSize, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QPixmap, QColor
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from ...base import BaseRenderer, emit_action, emit_action_spec
from ...icon import get_icon
from ..tasks.background_task_card import BackgroundTaskCard
from .common import (
    _clear_layout,
    _collection_items,
    _literal,
    _resolve_collection_index,
)
from .markdown_cleanup import normalize_markdown_for_qt
from ...collection_patch import patch_collection
from ..media.http import fetch_media_bytes

_ICON_COLOR_MUTED = "#71717a"
_ICON_COLOR_INFO = "#3b82f6"
_ICON_COLOR_SUCCESS = "#22c55e"
_ICON_COLOR_ERROR = "#ef4444"
_MESSAGE_LIST_BOTTOM_GAP = 56
_SCROLL_TO_BOTTOM_INTERVAL_MS = 1000
_SCROLL_TO_BOTTOM_SETTLE_MS = 120

# Icon name mapping for common action labels
_ACTION_ICONS: dict = {
    "copy": "ric.file-copy-line",
    "like": "ric.thumb-up-line",
    "dislike": "ric.thumb-down-line",
    "retry": "ric.refresh-line",
    "share": "ric.share-line",
    "delete": "ric.delete-bin-line",
    "edit": "ric.edit-line",
}


def _normalize_messages(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if value is None:
        return []
    return []


def _format_message_meta(value: Any) -> str:
    raw = _literal(value).strip()
    if not raw:
        return ""
    if len(raw) < 16 or raw[4:5] != "-" or raw[7:8] != "-":
        return raw
    candidate = raw.replace(" ", "T", 1)
    try:
        if candidate.endswith("Z"):
            parsed = datetime.fromisoformat(candidate[:-1] + "+00:00")
        else:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return raw
    return parsed.astimezone().strftime("%d/%m/%Y %H:%M")


def _parse_status_message_payload(raw_text: Any) -> dict[str, str] | None:
    payload: Any = raw_text
    if isinstance(payload, dict) and "literalString" in payload:
        payload = payload.get("literalString")
    if isinstance(payload, dict):
        candidate = payload
    else:
        text = str(payload or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1]).strip()
        try:
            candidate = json.loads(text)
        except Exception:
            return None
    if not isinstance(candidate, dict):
        return None
    status = str(candidate.get("status") or "").strip().lower()
    if status == "error":
        status = "ko"
    message = str(candidate.get("message") or "").strip()
    if status in {"ok", "ko"} and message:
        return {"status": status, "message": message}
    if status == "ko":
        error = str(candidate.get("error") or "").strip()
        if error:
            return {"status": "ko", "message": error}

    ok_value = candidate.get("ok")
    if isinstance(ok_value, bool):
        derived_status = "ok" if ok_value else "ko"
        if message:
            return {"status": derived_status, "message": message}
        error = str(candidate.get("error") or "").strip()
        if error:
            return {"status": "ko", "message": error}

        fragments: list[str] = []
        for key in ("status", "ingestion", "result", "detail"):
            value = str(candidate.get(key) or "").strip()
            if value:
                fragments.append(value.replace("_", " "))
        if fragments:
            return {"status": derived_status, "message": " - ".join(fragments)}
        return {
            "status": derived_status,
            "message": "Operazione completata" if ok_value else "Operazione fallita",
        }
    return None


def _compact_message_body(raw_text: Any, *, show_info_icon: bool = True) -> QWidget:
    payload = _parse_status_message_payload(raw_text)
    if payload is not None:
        status = payload["status"]
        text = payload["message"]
        icon_name = (
            "ric.checkbox-circle-line" if status == "ok" else "ric.close-circle-line"
        )
        icon_color = _ICON_COLOR_SUCCESS if status == "ok" else _ICON_COLOR_ERROR
        show_icon = True
    else:
        text = _literal(raw_text)
        icon_name = "ric.information-line"
        icon_color = _ICON_COLOR_INFO
        show_icon = show_info_icon

    wrapper = QWidget()
    layout = QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    icon_label: QLabel | None = None
    if show_icon:
        icon_label = QLabel()
        icon_label.setPixmap(get_icon(icon_name, icon_color, 16).pixmap(QSize(16, 16)))
        icon_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        icon_label.setProperty("ui_role", "advanced_message_status_icon")
        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

    text_label = QLabel(text)
    text_label.setWordWrap(True)
    text_label.setTextFormat(Qt.TextFormat.PlainText)
    text_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    text_label.setProperty("ui_role", "advanced_message_body")
    layout.addWidget(text_label, 1)

    wrapper._message_text_label = text_label  # type: ignore[attr-defined]
    wrapper._message_icon_label = icon_label  # type: ignore[attr-defined]
    wrapper._message_show_info_icon = show_info_icon  # type: ignore[attr-defined]
    return wrapper


def _update_compact_message_body(body: QWidget, raw_text: Any) -> bool:
    text_label = getattr(body, "_message_text_label", None)
    icon_label = getattr(body, "_message_icon_label", None)
    show_info_icon = bool(getattr(body, "_message_show_info_icon", True))
    if not isinstance(text_label, QLabel):
        return False

    payload = _parse_status_message_payload(raw_text)
    if payload is not None:
        status = payload["status"]
        text = payload["message"]
        icon_name = (
            "ric.checkbox-circle-line" if status == "ok" else "ric.close-circle-line"
        )
        icon_color = _ICON_COLOR_SUCCESS if status == "ok" else _ICON_COLOR_ERROR
        show_icon = True
    else:
        text = _literal(raw_text)
        icon_name = "ric.information-line"
        icon_color = _ICON_COLOR_INFO
        show_icon = show_info_icon

    text_label.setText(text)
    if show_icon and isinstance(icon_label, QLabel):
        icon_label.setPixmap(get_icon(icon_name, icon_color, 16).pixmap(QSize(16, 16)))
        icon_label.show()
    elif isinstance(icon_label, QLabel):
        icon_label.hide()
    return True


def _assistant_message_body(raw_text: Any) -> QWidget:
    if _parse_status_message_payload(raw_text) is not None:
        return _compact_message_body(raw_text, show_info_icon=False)
    assistant_body = _AutoResizeMarkdownBrowser()
    assistant_body.set_markdown(_literal(raw_text))
    assistant_body.setStyleSheet("background: transparent; border: none;")
    assistant_body.setProperty("ui_role", "advanced_message_body")
    return assistant_body


def _reasoning_block(
    message: Dict[str, Any],
) -> tuple[QFrame, _AutoResizeMarkdownBrowser, QToolButton] | None:
    reasoning = _literal(_message_reasoning(message)).strip()
    if not reasoning:
        return None
    reasoning_open = _reasoning_open_for_message(message)
    reasoning_wrap = QFrame()
    reasoning_layout = QVBoxLayout(reasoning_wrap)
    reasoning_layout.setContentsMargins(0, 2, 0, 0)
    reasoning_layout.setSpacing(4)

    reasoning_toggle = QToolButton()
    reasoning_toggle.setText("Reasoning")
    reasoning_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    reasoning_toggle.setCheckable(True)
    reasoning_toggle.setChecked(reasoning_open)
    reasoning_toggle.setArrowType(
        Qt.ArrowType.DownArrow if reasoning_open else Qt.ArrowType.RightArrow
    )
    reasoning_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
    reasoning_toggle.setProperty("ui_role", "advanced_message_action")
    reasoning_wrap.setProperty("ui_role", "advanced_reasoning_wrap")

    reasoning_body = _AutoResizeMarkdownBrowser()
    reasoning_body.set_markdown(reasoning)
    reasoning_body.setStyleSheet(
        "color: #a1a1aa; background: transparent; border: none;"
    )
    reasoning_body.setVisible(reasoning_open)

    reasoning_toggle.toggled.connect(
        lambda visible, widget=reasoning_body: widget.setVisible(bool(visible))
    )
    reasoning_toggle.toggled.connect(
        lambda visible, toggle=reasoning_toggle: toggle.setArrowType(
            Qt.ArrowType.DownArrow if bool(visible) else Qt.ArrowType.RightArrow
        )
    )
    reasoning_layout.addWidget(reasoning_toggle, 0, Qt.AlignmentFlag.AlignLeft)
    reasoning_layout.addWidget(reasoning_body)
    return reasoning_wrap, reasoning_body, reasoning_toggle


def _nearest_scroll_area(widget: QWidget) -> QScrollArea | None:
    target = widget.parentWidget()
    while target is not None and not isinstance(target, QScrollArea):
        if not shiboken6.isValid(target):
            return None
        target = target.parentWidget()
    if target is None or not shiboken6.isValid(target):
        return None
    return target


def _schedule_scroll_to_bottom(widget: QWidget, *, force: bool = False) -> None:
    if not force and not bool(getattr(widget, "_scroll_to_bottom_enabled", True)):
        return
    if force:
        widget._scroll_to_bottom_enabled = True  # type: ignore[attr-defined]
    if bool(getattr(widget, "_scroll_to_bottom_pending", False)):
        return
    widget._scroll_to_bottom_pending = True  # type: ignore[attr-defined]
    last_scroll_at = float(getattr(widget, "_last_scroll_to_bottom_at", 0.0) or 0.0)
    elapsed_ms = int((time.monotonic() - last_scroll_at) * 1000)
    delay_ms = max(0, _SCROLL_TO_BOTTOM_INTERVAL_MS - elapsed_ms)

    def _scroll_once(*, final: bool = False) -> None:
        if widget is None or not shiboken6.isValid(widget):
            return
        if final:
            widget._scroll_to_bottom_pending = False  # type: ignore[attr-defined]
        target = _nearest_scroll_area(widget)
        if target is None:
            return
        scrollbar = target.verticalScrollBar()
        maximum = scrollbar.maximum()
        if scrollbar.value() != maximum:
            widget._scroll_to_bottom_programmatic = True  # type: ignore[attr-defined]
            scrollbar.setValue(maximum)
            widget._scroll_to_bottom_programmatic = False  # type: ignore[attr-defined]
        widget._last_scroll_to_bottom_at = time.monotonic()  # type: ignore[attr-defined]

    QTimer.singleShot(delay_ms, lambda: _scroll_once(final=False))
    QTimer.singleShot(
        delay_ms + _SCROLL_TO_BOTTOM_SETTLE_MS,
        lambda: _scroll_once(final=True),
    )


def _is_near_scroll_bottom(widget: QWidget, threshold: int = 96) -> bool:
    target = _nearest_scroll_area(widget)
    if target is None:
        return True
    scrollbar = target.verticalScrollBar()
    return scrollbar.maximum() - scrollbar.value() <= threshold


def _schedule_preserve_scroll_after_prepend(
    widget: QWidget, old_value: int, old_maximum: int
) -> None:
    def _restore_once() -> None:
        if widget is None or not shiboken6.isValid(widget):
            return
        target = _nearest_scroll_area(widget)
        if target is None:
            return
        scrollbar = target.verticalScrollBar()
        scrollbar.setValue(old_value + max(0, scrollbar.maximum() - old_maximum))

    QTimer.singleShot(0, _restore_once)
    QTimer.singleShot(80, _restore_once)


def _schedule_attach_load_more_handler(widget: QWidget) -> None:
    def _attach() -> None:
        if widget is None or not shiboken6.isValid(widget):
            return
        action = getattr(widget, "_on_load_more", None)
        app_instance = getattr(widget, "_app_instance", None)
        if not isinstance(action, dict) or app_instance is None:
            return
        scroll_area = _nearest_scroll_area(widget)
        if scroll_area is None:
            return
        if (
            getattr(widget, "_load_more_scrollbar", None)
            is scroll_area.verticalScrollBar()
        ):
            return

        scrollbar = scroll_area.verticalScrollBar()
        widget._load_more_scrollbar = scrollbar  # type: ignore[attr-defined]
        widget._load_more_last_at = 0.0  # type: ignore[attr-defined]

        def _on_scroll(value: int) -> None:
            if value > 32:
                return
            now = time.monotonic()
            last_at = float(getattr(widget, "_load_more_last_at", 0.0) or 0.0)
            if now - last_at < 0.7:
                return
            widget._load_more_last_at = now  # type: ignore[attr-defined]
            emit_action_spec(
                app_instance,
                action,
                {"target": widget.objectName(), "source": "scroll_top"},
                getattr(widget, "_surface_id", "main"),
                getattr(widget, "_comp_id", widget.objectName()),
            )

        scrollbar.valueChanged.connect(_on_scroll)

    QTimer.singleShot(0, _attach)
    QTimer.singleShot(80, _attach)


def _schedule_attach_scroll_to_bottom_button(widget: QWidget) -> None:
    def _attach() -> None:
        if widget is None or not shiboken6.isValid(widget):
            return
        scroll_area = _nearest_scroll_area(widget)
        if scroll_area is None:
            return
        viewport = scroll_area.viewport()
        button = getattr(widget, "_scroll_bottom_button", None)
        if button is None or not shiboken6.isValid(button):
            button = QToolButton(viewport)
            button.setIcon(get_icon("ric.arrow-down-line", _ICON_COLOR_MUTED, 16))
            button.setIconSize(QSize(16, 16))
            button.setToolTip("Scroll to bottom")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("ui_role", "advanced_message_action")
            button.setFixedSize(36, 36)
            button.clicked.connect(
                lambda: _schedule_scroll_to_bottom(widget, force=True)
            )
            widget._scroll_bottom_button = button  # type: ignore[attr-defined]

        def _sync(_value: int | None = None) -> None:
            if not shiboken6.isValid(button):
                return
            scrollbar = scroll_area.verticalScrollBar()
            visible = scrollbar.maximum() - scrollbar.value() > 160
            button.move(
                max(0, int((viewport.width() - button.width()) / 2)),
                max(0, viewport.height() - button.height() - 16),
            )
            button.setVisible(visible)
            if visible:
                button.raise_()

        def _track_scroll_intent(value: int) -> None:
            if bool(getattr(widget, "_scroll_to_bottom_programmatic", False)):
                return
            scrollbar = scroll_area.verticalScrollBar()
            if scrollbar.maximum() - value <= 96:
                widget._scroll_to_bottom_enabled = True  # type: ignore[attr-defined]
                return
            widget._scroll_to_bottom_enabled = False  # type: ignore[attr-defined]

        scrollbar = scroll_area.verticalScrollBar()
        if getattr(widget, "_scroll_bottom_scrollbar", None) is not scrollbar:
            widget._scroll_bottom_scrollbar = scrollbar  # type: ignore[attr-defined]
            scrollbar.valueChanged.connect(_sync)
            scrollbar.valueChanged.connect(_track_scroll_intent)
        _sync()

    QTimer.singleShot(0, _attach)


def _message_list_bottom_spacer() -> QWidget:
    spacer = QWidget()
    spacer.setObjectName("chat_message_list_bottom_gap")
    spacer.setFixedHeight(_MESSAGE_LIST_BOTTOM_GAP)
    spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    spacer.setStyleSheet("background: transparent; border: none;")
    return spacer


def _add_message_list_bottom_spacer(widget: QWidget, layout: QVBoxLayout) -> None:
    spacer = _message_list_bottom_spacer()
    widget._messages_bottom_spacer = spacer  # type: ignore[attr-defined]
    layout.addWidget(spacer)


class _AutoResizeMarkdownBrowser(QTextBrowser):
    _DEBOUNCE_MS = 70

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_height = -1
        self._pending_markdown = ""
        self._applied_markdown = ""
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._apply_pending_markdown)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.setOpenLinks(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = self.document().documentLayout()
        if layout is not None:
            layout.documentSizeChanged.connect(lambda *_: self._sync_height())

    def set_markdown(self, text: str) -> None:
        normalized = normalize_markdown_for_qt(str(text or ""))
        self._pending_markdown = normalized
        if self._applied_markdown == "":
            self._apply_pending_markdown()
            return
        if not self._debounce_timer.isActive():
            self._debounce_timer.start(self._DEBOUNCE_MS)

    def flush_markdown(self) -> None:
        if self._debounce_timer.isActive():
            self._debounce_timer.stop()
        self._apply_pending_markdown()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._sync_height()

    def _sync_height(self) -> None:
        viewport_width = max(0, int(self.viewport().width()))
        if viewport_width > 0:
            self.document().setTextWidth(float(viewport_width))
        doc_size = self.document().documentLayout().documentSize()
        new_height = max(
            24,
            int(math.ceil(float(doc_size.height()))) + (self.frameWidth() * 2) + 2,
        )
        if new_height == self._last_height:
            return
        self._last_height = new_height
        self.setFixedHeight(new_height)

    def _apply_pending_markdown(self) -> None:
        if self._pending_markdown == self._applied_markdown:
            return
        self.setMarkdown(self._pending_markdown)
        self._applied_markdown = self._pending_markdown
        self._sync_height()


def _current_module_name(app_instance: Any) -> str:
    current = app_instance
    visited = 0
    while current is not None and visited < 10:
        store = getattr(current, "store", None)
        if store is not None and hasattr(store, "get"):
            try:
                path = str(store.get("/current_path", "/", "global") or "/")
            except Exception:
                path = "/"
            parts = [part for part in path.split("/") if part]
            if parts:
                return str(parts[0] or "").strip() or "dashboard"
        parent_getter = getattr(current, "parent", None)
        if callable(parent_getter):
            current = parent_getter()
        else:
            break
        visited += 1
    return "dashboard"


def _media_proxy_path(app_instance: Any, target: str) -> str:
    return "/media/proxy?" + urlencode(
        {
            "module_name": _current_module_name(app_instance),
            "url": str(target or "").strip(),
        }
    )


def _load_by_file_id_http(file_id: str, app_instance: Any) -> bytes:
    fid = str(file_id or "").strip()
    if not fid:
        return b""
    request_path = _media_proxy_path(app_instance, f"/media/uploads/{fid}")
    payload = fetch_media_bytes(app_instance, request_path, timeout=15.0)
    return payload


def _load_by_media_path_http(path: str, app_instance: Any) -> bytes:
    raw_path = str(path or "").strip()
    if not raw_path.startswith("/media/"):
        return b""
    request_path = (
        raw_path
        if raw_path.startswith("/media/proxy")
        else _media_proxy_path(app_instance, raw_path)
    )
    payload = fetch_media_bytes(app_instance, request_path, timeout=15.0)
    return payload


def _load_attachment_bytes(
    path: str, *, file_id: str = "", app_instance: Any = None
) -> bytes:
    if app_instance is not None and str(file_id or "").strip():
        payload = _load_by_file_id_http(str(file_id), app_instance)
        if payload:
            return payload
    if app_instance is not None:
        payload = _load_by_media_path_http(str(path), app_instance)
        if payload:
            return payload
    local_path = str(path or "").strip()
    if local_path:
        try:
            resolved = Path(local_path).expanduser()
            if resolved.exists() and resolved.is_file():
                payload = resolved.read_bytes()
                return payload
        except Exception:
            return b""
    return b""


def _is_previewable_mime(mime: str) -> bool:
    normalized = str(mime or "").strip().lower()
    return normalized.startswith("image/") or normalized == "application/pdf"


def _message_attachments(message: Dict[str, Any]) -> list[Dict[str, str]]:
    content = _message_content(message)
    attachments = content.get("attachments")
    if not isinstance(attachments, list):
        attachments = message.get("attachments")
    if not isinstance(attachments, list):
        return []
    rows: list[Dict[str, str]] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        file_id = str(item.get("file_id") or "").strip()
        storage_path = str(item.get("storage_path") or "").strip()
        url = str(item.get("url") or "").strip()
        name = str(item.get("name") or os.path.basename(storage_path)).strip()
        mime_hint = storage_path
        mime = (
            str(item.get("mime_type") or mimetypes.guess_type(mime_hint)[0] or "")
            .strip()
            .lower()
        )
        if name:
            rows.append(
                {
                    "name": name,
                    "mime_type": mime,
                    "storage_path": storage_path,
                    "file_id": file_id,
                    "url": url,
                }
            )
    return rows


def _normalize_surface_components(message: Dict[str, Any]) -> list[dict]:
    content = _message_content(message)
    raw = content.get("components")
    if not isinstance(raw, list):
        single = content.get("component")
        if isinstance(single, dict):
            raw = [single]
    if not isinstance(raw, list):
        raw = message.get("surface_components")
    if not isinstance(raw, list):
        raw = message.get("components")
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for entry in raw:
        if isinstance(entry, dict) and isinstance(entry.get("component"), dict):
            out.append(dict(entry))
    return out


def _message_content(message: Dict[str, Any]) -> dict:
    content = message.get("content")
    return content if isinstance(content, dict) else {}


def _message_kind(message: Dict[str, Any]) -> str:
    return str(message.get("kind") or "text").strip().lower() or "text"


def _message_text(message: Dict[str, Any]) -> Any:
    content = _message_content(message)
    if "text" in content:
        return content.get("text")
    if "summary" in content:
        return content.get("summary")
    return message.get("text", "")


def _message_reasoning(message: Dict[str, Any]) -> Any:
    content = _message_content(message)
    if "reasoning" in content:
        return content.get("reasoning")
    return message.get("reasoning", "")


def _reasoning_open_for_message(message: Dict[str, Any]) -> bool:
    return (
        str(message.get("status") or "").strip().lower() == "streaming"
        and not _literal(_message_text(message)).strip()
    )


def _message_task_id(message: Dict[str, Any]) -> str:
    content = _message_content(message)
    meta = message.get("meta")
    meta_task_id = meta.get("task_id") if isinstance(meta, dict) else ""
    return str(
        content.get("task_id") or message.get("task_id") or meta_task_id or ""
    ).strip()


def _make_ids_unique(comp_def: dict, suffix: str) -> None:
    comp_id = str(comp_def.get("id") or "").strip()
    if comp_id:
        comp_def["id"] = f"{comp_id}_{suffix}"

    component = comp_def.get("component")
    if not isinstance(component, dict) or not component:
        return
    c_type = list(component.keys())[0]
    comp_props = component.get(c_type) or {}
    if c_type == "Tabs" and isinstance(comp_props, dict):
        tabs = comp_props.get("tabs")
        if isinstance(tabs, list):
            comp_props["tabs"] = [
                (
                    {**tab, "id": f"{str(tab.get('id')).strip()}_{suffix}"}
                    if isinstance(tab, dict) and str(tab.get("id") or "").strip()
                    else tab
                )
                for tab in tabs
            ]
    children_node = comp_def.get("children") or comp_props.get("children", {})

    if isinstance(children_node, dict) and "explicitList" in children_node:
        for child in list(children_node.get("explicitList") or []):
            if isinstance(child, dict):
                _make_ids_unique(child, suffix)


def _build_message_surface_widget(
    *,
    message: Dict[str, Any],
    surface_id: str,
    app_instance: Any,
) -> QWidget | None:
    components = _normalize_surface_components(message)
    if not components:
        return None

    message_id = str(message.get("id") or "").strip() or "message"
    inline_children: list[dict] = []
    for index, entry in enumerate(components):
        cloned = dict(entry)
        _make_ids_unique(cloned, f"{message_id}_{index}")
        inline_children.append(cloned)

    root_def = {
        "id": f"{message_id}_surface_root",
        "component": {"Row": {"spacing": 8}},
        "children": {"explicitList": inline_children},
    }
    try:
        return app_instance.renderer.build_widget(
            surface_id,
            app_instance.surfaces,
            comp_def=root_def,
            item=message,
            app_instance=app_instance,
        )
    except Exception:
        return None


def _pdf_first_page_pixmap(payload: bytes, max_width: int) -> QPixmap | None:
    try:
        import pypdfium2 as pdfium
    except Exception:
        return None
    try:
        doc = pdfium.PdfDocument(payload)
        if len(doc) < 1:
            return None
        page = doc[0]
        pil_img = page.render(scale=2.0).to_pil()
        from PySide6.QtGui import QImage

        data = pil_img.tobytes("raw", "RGBA")
        qimage = QImage(
            data,
            pil_img.width,
            pil_img.height,
            QImage.Format.Format_RGBA8888,
        ).copy()
        pix = QPixmap.fromImage(qimage)
        return pix.scaledToWidth(
            max(240, int(max_width)),
            Qt.TransformationMode.SmoothTransformation,
        )
    except Exception:
        return None


def _write_temp_pdf_file(payload: bytes) -> str:
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".pdf",
            prefix="chat-preview-",
            delete=False,
        ) as handle:
            handle.write(payload)
            return str(handle.name)
    except Exception:
        return ""


def _build_pdf_qml_viewer(payload: bytes) -> tuple[QWidget | None, str]:
    try:
        from PySide6.QtQuickWidgets import QQuickWidget
    except Exception:
        return None, ""
    pdf_path = _write_temp_pdf_file(payload)
    if not pdf_path:
        return None, ""
    qml_path = Path(__file__).with_name("pdf_viewer.qml")
    if not qml_path.exists():
        return None, pdf_path
    try:
        widget = QQuickWidget()
        widget.setClearColor(QColor("#ffffff"))
        widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        widget.rootContext().setContextProperty(
            "pdfSourceUrl", QUrl.fromLocalFile(pdf_path)
        )
        widget.setSource(QUrl.fromLocalFile(str(qml_path)))
        if widget.status() == QQuickWidget.Status.Error:
            try:
                errs = [str(err.toString()) for err in list(widget.errors() or [])]
            except Exception:
                errs = []
            return None, pdf_path
        widget.setMinimumHeight(320)
        return widget, pdf_path
    except Exception:
        return None, pdf_path


def _attachment_row_widget(
    *,
    app_instance: Any,
    attachment: Dict[str, str],
    on_attachment_click: Dict[str, Any] | None = None,
    surface_id: str = "",
    comp_id: str = "",
    message: Dict[str, Any] | None = None,
) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    name = str(attachment.get("name") or "").strip()
    mime_type = str(attachment.get("mime_type") or "").strip().lower()
    can_preview = _is_previewable_mime(mime_type)

    name_label = QLabel()
    name_label.setWordWrap(True)
    name_label.setProperty("ui_role", "advanced_message_meta")
    if can_preview:
        escaped = html.escape(name)
        name_label.setText(f'<a href="preview://open">{escaped}</a>')
        name_label.setTextFormat(Qt.TextFormat.RichText)
        name_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        name_label.setOpenExternalLinks(False)

        def _open_preview(_link: str) -> None:
            if isinstance(on_attachment_click, dict):
                if str(on_attachment_click.get("name") or "").strip():
                    emit_action_spec(
                        app_instance,
                        on_attachment_click,
                        {
                            "message_id": str((message or {}).get("id") or ""),
                            "message_role": str((message or {}).get("role") or ""),
                            "name": name,
                            "mime_type": mime_type,
                            "storage_path": str(attachment.get("storage_path") or ""),
                            "file_id": str(attachment.get("file_id") or ""),
                            "url": str(attachment.get("url") or ""),
                        },
                        surface_id,
                        comp_id,
                    )
            return

        name_label.linkActivated.connect(_open_preview)
    else:
        name_label.setText(name)
        name_label.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(name_label)
    layout.addStretch()
    return row


# ── Shared message card ───────────────────────────────────────────────────────


def _message_card(
    message: Dict[str, Any],
    surface_id: str,
    app_instance: Any,
    comp_id: str,
    on_attachment_click: Dict[str, Any] | None = None,
) -> QWidget:
    outer = QFrame()
    outer.setObjectName(comp_id)
    outer._surface_id = surface_id  # type: ignore[attr-defined]
    outer._app_instance = app_instance  # type: ignore[attr-defined]
    outer._comp_id = comp_id  # type: ignore[attr-defined]
    outer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    row = QHBoxLayout(outer)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    row.setAlignment(Qt.AlignmentFlag.AlignTop)

    role = str(message.get("role", "assistant"))
    kind = _message_kind(message)
    is_user = role == "user"
    is_tool = role == "tool" or kind in {"tool_call", "tool_result"}
    is_component = kind == "component"
    message_id = str(message.get("id") or "").strip()

    if role == "task" or kind == "task":
        task_id = _message_task_id(message)
        if task_id:
            card = BackgroundTaskCard(
                task_id=task_id,
                event_actions=None,
                store=app_instance.store,
                app_instance=app_instance,
                surface_id=surface_id,
                comp_id=comp_id,
                send_action=app_instance._action.send_action,
            )
            card.setObjectName(comp_id)
            return card
        task_frame = QFrame()
        task_frame.setProperty("ui_role", "advanced_message_task")
        task_layout = QVBoxLayout(task_frame)
        task_layout.setContentsMargins(12, 10, 12, 10)
        task_layout.setSpacing(4)
        content = _message_content(message)
        title = QLabel(str(content.get("title") or message.get("title") or "Task"))
        title.setProperty("ui_role", "advanced_message_body")
        status = QLabel(str(message.get("status") or "pending"))
        status.setProperty("ui_role", "advanced_message_meta")
        task_layout.addWidget(title)
        task_layout.addWidget(status)
        return task_frame

    if is_component:
        message_surface = _build_message_surface_widget(
            message=message,
            surface_id=surface_id,
            app_instance=app_instance,
        )
        if message_surface is not None:
            message_surface.setObjectName(message_id or comp_id)
            message_surface.setProperty("ui_role", "advanced_message_component")
            outer._message_id = message_id  # type: ignore[attr-defined]
            outer._message_role = role  # type: ignore[attr-defined]
            row.addWidget(message_surface, 0)
            row.addStretch()

            def _sync_component_width() -> None:
                available = max(320, int(outer.width() or 0))
                target = max(320, int(available * 0.80))
                message_surface.setMinimumWidth(target)
                message_surface.setMaximumWidth(target)

            outer.resizeEvent = lambda event: (
                QFrame.resizeEvent(outer, event),
                _sync_component_width(),
            )
            _sync_component_width()
            return outer
        outer._message_id = message_id  # type: ignore[attr-defined]
        outer._message_role = role  # type: ignore[attr-defined]
        return outer

    bubble = QFrame()
    bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    bubble.setMaximumWidth(980)
    bubble.setProperty("message_role", role)
    bubble.setProperty("ui_role", "advanced_message_bubble")
    bubble_layout = QVBoxLayout(bubble)
    bubble_layout.setContentsMargins(12, 10, 12, 10)
    bubble_layout.setSpacing(6)
    outer._message_bubble_layout = bubble_layout  # type: ignore[attr-defined]

    top_row = QHBoxLayout()
    top_row.setContentsMargins(0, 0, 0, 0)
    top_row.setSpacing(6)
    if not is_tool:
        role_label = QLabel("User" if is_user else "Assistant")
        role_label.setProperty("ui_role", "advanced_message_meta")
        top_row.addWidget(role_label)

    copied_label = QLabel("")
    copied_label.setProperty("ui_role", "advanced_message_meta")

    copy_btn = QToolButton()
    copy_btn.setIcon(
        get_icon(_ACTION_ICONS.get("copy", "ric.file-copy-line"), _ICON_COLOR_MUTED, 14)
    )
    copy_btn.setIconSize(QSize(14, 14))
    copy_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    copy_btn.setToolTip("Copy")
    copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    copy_btn.setProperty("ui_role", "message_action_icon_btn")

    def _copy_message_text() -> None:
        QGuiApplication.clipboard().setText(_literal(_message_text(message)))
        copied_label.setText("Copied")
        QTimer.singleShot(1200, lambda: copied_label.setText(""))

    copy_btn.clicked.connect(_copy_message_text)
    if not is_tool:
        top_row.addWidget(copy_btn)
        top_row.addWidget(copied_label)
    top_row.addStretch()
    if not is_tool:
        bubble_layout.addLayout(top_row)

    reasoning = None if is_user else _reasoning_block(message)
    if reasoning is not None:
        reasoning_wrap, reasoning_body, reasoning_toggle = reasoning
        bubble_layout.addWidget(reasoning_wrap)
        outer._message_reasoning_body_widget = reasoning_body  # type: ignore[attr-defined]
        outer._message_reasoning_toggle_widget = reasoning_toggle  # type: ignore[attr-defined]

    # Body
    body: QWidget
    if is_user:
        user_body = QLabel(_literal(_message_text(message)))
        user_body.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        user_body.setWordWrap(True)
        user_body.setTextFormat(Qt.TextFormat.PlainText)
        body = user_body
    elif is_tool:
        body = _compact_message_body(
            _message_text(message),
            show_info_icon=True,
        )
    else:
        body = _assistant_message_body(_message_text(message))

    if isinstance(body, QLabel):
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setProperty("ui_role", "advanced_message_body")
    bubble_layout.addWidget(body)
    outer._message_body_widget = body  # type: ignore[attr-defined]
    outer._message_role = role  # type: ignore[attr-defined]
    outer._message_id = str(message.get("id") or "")  # type: ignore[attr-defined]

    attachments = _message_attachments(message)
    if not isinstance(on_attachment_click, dict):
        fallback_click = message.get("on_attachment_click")
        on_attachment_click = (
            fallback_click if isinstance(fallback_click, dict) else None
        )
    if attachments:
        for attachment in attachments:
            bubble_layout.addWidget(
                _attachment_row_widget(
                    app_instance=app_instance,
                    attachment=attachment,
                    on_attachment_click=on_attachment_click,
                    surface_id=surface_id,
                    comp_id=comp_id,
                    message=message,
                )
            )

    if message_id:
        message_surface = _build_message_surface_widget(
            message=message,
            surface_id=surface_id,
            app_instance=app_instance,
        )
        if message_surface is not None:
            message_surface.setObjectName(f"{message_id}_surface")
            message_surface.setProperty("ui_role", "advanced_message_surface")
            bubble_layout.addWidget(message_surface)

    # Footer: meta + copy action
    footer = QHBoxLayout()
    footer.setContentsMargins(0, 2, 0, 0)
    footer.setSpacing(8)

    meta_text = _format_message_meta(message.get("meta", message.get("created_at", "")))
    if meta_text:
        meta = QLabel(meta_text)
        meta.setProperty("ui_role", "advanced_message_meta")
        footer.addWidget(meta)

    footer.addStretch()

    # Inline action icon buttons
    actions = message.get("actions", []) or []
    for action_def in actions:
        label = str(action_def.get("label", ""))
        # Resolve icon: explicit 'icon' field, or map from label, or fallback
        icon_name = action_def.get("icon") or _ACTION_ICONS.get(
            label.lower(), "ric.more-line"
        )
        if not icon_name.startswith("ric."):
            icon_name = f"ric.{icon_name}"
        btn = QToolButton()
        btn.setIcon(get_icon(icon_name, _ICON_COLOR_MUTED, 14))
        btn.setIconSize(QSize(14, 14))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setToolTip(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("ui_role", "message_action_icon_btn")
        payload = action_def.get("action", {})
        btn.clicked.connect(
            lambda _=False, payload=payload: emit_action_spec(
                app_instance,
                payload,
                {},
                surface_id,
                comp_id,
            )
        )
        footer.addWidget(btn)

    bubble_layout.addLayout(footer)

    if is_user:
        row.addStretch()
        row.addWidget(bubble, 0)
    else:
        row.addWidget(bubble, 0)
        row.addStretch()

    def _sync_bubble_width() -> None:
        available = max(320, int(outer.width() or 0))
        target = max(320, int(available * 0.88))
        bubble.setMinimumWidth(target)
        bubble.setMaximumWidth(target)

    outer.resizeEvent = lambda event: (
        QFrame.resizeEvent(outer, event),
        _sync_bubble_width(),
    )
    _sync_bubble_width()

    return outer


def _sync_reasoning_visibility(
    toggle: Any,
    body: _AutoResizeMarkdownBrowser,
    message: Dict[str, Any],
) -> None:
    open_reasoning = (
        str(message.get("status") or "").strip().lower() == "streaming"
        and not _literal(_message_text(message)).strip()
    )
    if isinstance(toggle, QToolButton):
        toggle.setChecked(open_reasoning)
        toggle.setArrowType(
            Qt.ArrowType.DownArrow if open_reasoning else Qt.ArrowType.RightArrow
        )
    body.setVisible(open_reasoning)


def _update_message_card_in_place(card: QWidget, replacement: Dict[str, Any]) -> bool:
    body = getattr(card, "_message_body_widget", None)
    reasoning_body = getattr(card, "_message_reasoning_body_widget", None)
    reasoning_toggle = getattr(card, "_message_reasoning_toggle_widget", None)
    role = str(getattr(card, "_message_role", "") or "")
    if body is None or role not in {"user", "assistant", "tool"}:
        return False
    text = str(_message_text(replacement) or "")
    reasoning = _literal(_message_reasoning(replacement)).strip()
    if reasoning and reasoning_body is None:
        return False
    if isinstance(body, QLabel):
        body.setText(text)
        if isinstance(reasoning_body, _AutoResizeMarkdownBrowser):
            reasoning_body.set_markdown(reasoning)
            _sync_reasoning_visibility(reasoning_toggle, reasoning_body, replacement)
        card._message_id = str(replacement.get("id") or "")  # type: ignore[attr-defined]
        return True
    if role == "assistant" and isinstance(body, _AutoResizeMarkdownBrowser):
        if _parse_status_message_payload(text) is not None:
            return False
        body.set_markdown(text)
        if isinstance(reasoning_body, _AutoResizeMarkdownBrowser):
            reasoning_body.set_markdown(reasoning)
            _sync_reasoning_visibility(reasoning_toggle, reasoning_body, replacement)
        card._message_id = str(replacement.get("id") or "")  # type: ignore[attr-defined]
        return True
    if role in {"assistant", "tool"} and isinstance(body, QWidget):
        if role == "assistant" and _parse_status_message_payload(text) is None:
            return False
        if _update_compact_message_body(body, text):
            if isinstance(reasoning_body, _AutoResizeMarkdownBrowser):
                reasoning_body.set_markdown(reasoning)
                _sync_reasoning_visibility(
                    reasoning_toggle, reasoning_body, replacement
                )
            card._message_id = str(replacement.get("id") or "")  # type: ignore[attr-defined]
            return True
    return False


def _supports_text_only_replace(
    current: Dict[str, Any], replacement: Dict[str, Any]
) -> bool:
    stable_keys = (
        "id",
        "role",
        "meta",
        "attachments",
        "actions",
        "surface_components",
        "components",
        "kind",
    )
    for key in stable_keys:
        if current.get(key) != replacement.get(key):
            return False
    if _message_text(current) != _message_text(replacement):
        return True
    if _message_reasoning(current) != _message_reasoning(replacement):
        return True
    if current.get("content") != replacement.get("content"):
        return False
    return True


# ── MessageListRenderer ───────────────────────────────────────────────────────


class MessageListRenderer(BaseRenderer):
    component_type = "MessageList"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "messages": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        frame = QFrame()
        frame.setObjectName(comp_id)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        root_layout = QVBoxLayout(frame)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(8)
        root_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        messages = _normalize_messages(props.get("messages"))
        on_attachment_click = props.get("on_attachment_click")
        if not isinstance(on_attachment_click, dict):
            on_attachment_click = None
        on_load_more = props.get("on_load_more")
        if not isinstance(on_load_more, dict):
            on_load_more = None
        download_enabled = bool(props.get("download_enabled", False))
        download_filename = (
            str(props.get("download_filename") or "messages.json").strip()
            or "messages.json"
        )

        if download_enabled:
            toolbar = QWidget()
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(0, 0, 0, 0)
            toolbar_layout.setSpacing(8)
            toolbar_layout.addStretch()
            download_btn = QPushButton("Download")
            download_btn.setProperty("ui_role", "advanced_message_action")

            def _download() -> None:
                current_messages = list(getattr(frame, "_messages", []) or [])
                default_name = download_filename
                filename, _ = QFileDialog.getSaveFileName(
                    frame,
                    "Save chat messages",
                    default_name,
                    "JSON Files (*.json);;Text Files (*.txt);;All Files (*)",
                )
                if not filename:
                    return
                try:
                    if filename.lower().endswith(".txt"):
                        lines: list[str] = []
                        for msg in current_messages:
                            role = str(msg.get("role") or "assistant")
                            text = str(_message_text(msg) or "")
                            lines.append(f"[{role}] {text}")
                        Path(filename).write_text("\n\n".join(lines), encoding="utf-8")
                    else:
                        Path(filename).write_text(
                            json.dumps(current_messages, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                except Exception:
                    return

            download_btn.clicked.connect(_download)
            toolbar_layout.addWidget(download_btn)
            root_layout.addWidget(toolbar)

        list_container = QFrame()
        layout = QVBoxLayout(list_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        frame._messages = messages  # type: ignore[attr-defined]
        frame._surface_id = surface_id  # type: ignore[attr-defined]
        frame._app_instance = app_instance  # type: ignore[attr-defined]
        frame._comp_id = comp_id  # type: ignore[attr-defined]
        frame._on_attachment_click = on_attachment_click  # type: ignore[attr-defined]
        frame._on_load_more = on_load_more  # type: ignore[attr-defined]
        frame._messages_layout = layout  # type: ignore[attr-defined]
        for message in messages:
            layout.addWidget(
                _message_card(
                    message,
                    surface_id,
                    app_instance,
                    comp_id,
                    on_attachment_click=on_attachment_click,
                )
            )
        _add_message_list_bottom_spacer(frame, layout)
        root_layout.addWidget(list_container)
        if messages:
            _schedule_scroll_to_bottom(frame)
        if on_load_more:
            _schedule_attach_load_more_handler(frame)
        _schedule_attach_scroll_to_bottom_button(frame)
        return frame

    def apply_collection_patch(
        self,
        widget: QWidget,
        prop: str,
        action: str,
        value: Any,
    ) -> bool:
        if prop != "messages":
            return False
        messages = list(getattr(widget, "_messages", []))
        layout = getattr(widget, "_messages_layout", None)
        if layout is None:
            return False

        patch = patch_collection(messages, action, value)
        if not patch.handled:
            return False

        sid = getattr(widget, "_surface_id", "main")
        ai = getattr(widget, "_app_instance", None)
        cid = getattr(widget, "_comp_id", widget.objectName())
        on_attachment_click = getattr(widget, "_on_attachment_click", None)

        if action == "append":
            for message in patch.appended or []:
                insert_index = len(messages)
                messages.append(message)
                layout.insertWidget(
                    insert_index,
                    _message_card(
                        message,
                        sid,
                        ai,
                        cid,
                        on_attachment_click=on_attachment_click,
                    ),
                )
            widget._messages = messages  # type: ignore[attr-defined]
            if patch.appended:
                _schedule_scroll_to_bottom(widget)
            return True

        if action == "prepend":
            scroll_area = _nearest_scroll_area(widget)
            old_value = 0
            old_maximum = 0
            if scroll_area is not None:
                scrollbar = scroll_area.verticalScrollBar()
                old_value = scrollbar.value()
                old_maximum = scrollbar.maximum()
            for index, message in enumerate(patch.appended or []):
                messages.insert(index, message)
                layout.insertWidget(
                    index,
                    _message_card(
                        message,
                        sid,
                        ai,
                        cid,
                        on_attachment_click=on_attachment_click,
                    ),
                )
            widget._messages = messages  # type: ignore[attr-defined]
            if patch.appended:
                _schedule_preserve_scroll_after_prepend(widget, old_value, old_maximum)
            return True

        if action == "remove":
            index = patch.index
            if index is None:
                return True
            messages.pop(index)
            item = layout.takeAt(index)
            if item:
                item_widget = item.widget()
                if item_widget is not None:
                    item_widget.setParent(None)
                    item_widget.deleteLater()
            widget._messages = messages  # type: ignore[attr-defined]
            return True

        if action == "replace":
            index = patch.index
            replacement = patch.replacement
            if index is None or replacement is None:
                return True
            was_near_bottom = _is_near_scroll_bottom(widget)
            replacement_id = str((replacement or {}).get("id") or "")
            existing_item = layout.itemAt(index)
            existing_widget = existing_item.widget() if existing_item else None
            existing_id = (
                str(getattr(existing_widget, "_message_id", "") or "")
                if existing_widget is not None
                else ""
            )
            if (
                existing_widget is not None
                and replacement_id
                and existing_id == replacement_id
                and index < len(messages)
                and _supports_text_only_replace(messages[index], replacement)
                and _update_message_card_in_place(existing_widget, replacement)
            ):
                messages[index] = replacement
                widget._messages = messages  # type: ignore[attr-defined]
                if was_near_bottom:
                    _schedule_scroll_to_bottom(widget)
                return True
            messages[index] = replacement
            old_item = layout.takeAt(index)
            if old_item:
                old_widget = old_item.widget()
                if old_widget is not None:
                    old_widget.setParent(None)
                    old_widget.deleteLater()
            layout.insertWidget(
                index,
                _message_card(
                    replacement,
                    sid,
                    ai,
                    cid,
                    on_attachment_click=on_attachment_click,
                ),
            )
            widget._messages = messages  # type: ignore[attr-defined]
            if was_near_bottom:
                _schedule_scroll_to_bottom(widget)
            return True

        if action == "set":
            previous_messages = list(getattr(widget, "_messages", []) or [])
            previous_count = len(previous_messages)
            previous_first = (
                str((previous_messages[0] or {}).get("id") or "")
                if previous_messages
                else ""
            )
            previous_last = (
                str((previous_messages[-1] or {}).get("id") or "")
                if previous_messages
                else ""
            )
            messages = list(patch.items)
            next_first = str((messages[0] or {}).get("id") or "") if messages else ""
            next_last = str((messages[-1] or {}).get("id") or "") if messages else ""
            scroll_area = _nearest_scroll_area(widget)
            old_value = 0
            old_maximum = 0
            if scroll_area is not None:
                scrollbar = scroll_area.verticalScrollBar()
                old_value = scrollbar.value()
                old_maximum = scrollbar.maximum()
            _clear_layout(layout)
            for message in messages:
                layout.addWidget(
                    _message_card(
                        message,
                        sid,
                        ai,
                        cid,
                        on_attachment_click=on_attachment_click,
                    )
                )
            _add_message_list_bottom_spacer(widget, layout)
            widget._messages = messages  # type: ignore[attr-defined]
            prepended = (
                previous_last
                and previous_last == next_last
                and previous_first != next_first
            )
            appended = previous_last != next_last
            if len(messages) > previous_count and prepended:
                _schedule_preserve_scroll_after_prepend(widget, old_value, old_maximum)
            elif len(messages) > previous_count and appended:
                _schedule_scroll_to_bottom(widget)
            return True

        return True

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "messages":
            self.apply_collection_patch(widget, prop, "set", _normalize_messages(value))
            return
        super().update_widget_property(widget, prop, value)
