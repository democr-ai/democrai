from __future__ import annotations
import mimetypes
import os
import tempfile
import time
from typing import Any, Dict, List
from PySide6.QtCore import QLocale, QMimeData, Qt, QSize, QUrl
from PySide6.QtGui import QAction, QDoubleValidator, QImage, QIntValidator, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel,
    QComboBox, QLineEdit, QMenu, QTextEdit, QToolButton, QVBoxLayout,
    QWidget, QWidgetAction,
)
from ...base import BaseRenderer, confirm_action, emit_action, emit_action_spec, publish_bound_value
from ...icon import get_icon
from ..forms.attachment import _infer_module_name, _upload_file_to_media_storage

# ── Remixicon names used in the composer ─────────────────────────────────────
_ICON_ATTACH = "ric.attachment-line"
_ICON_MIC    = "ric.mic-line"
_ICON_MIC_ON = "ric.mic-fill"
_ICON_STOP   = "ric.stop-circle-line"
_ICON_SEND   = "ric.send-plane-fill"
_ICON_SETTINGS = "ric.settings-3-line"
_ICON_COLOR_MUTED  = "#71717a"   # @text-disabled
_ICON_COLOR_SEND   = "#ffffff"
_ICON_COLOR_DANGER = "#ef4444"

# ── Icon helpers ──────────────────────────────────────────────────────────────

def _file_dialog_filter(accept: str) -> str:
    patterns: list[str] = []
    for mime_type in [item.strip() for item in str(accept or "").split(",") if item.strip()]:
        patterns.extend(f"*{ext}" for ext in mimetypes.guess_all_extensions(mime_type))
    if not patterns:
        return ""
    return f"Supported files ({' '.join(sorted(set(patterns)))})"

def _icon_btn(icon_name: str, tooltip: str, object_name: str,
              color: str = _ICON_COLOR_MUTED, size: int = 32) -> QToolButton:
    """Square icon-only toolbar button using a Remixicon glyph."""
    btn = QToolButton()
    btn.setIcon(get_icon(icon_name, color, 18))
    btn.setIconSize(QSize(18, 18))
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    btn.setToolTip(tooltip)
    btn.setObjectName(object_name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(size, size)
    btn.setProperty("ui_role", "composer_icon_btn")
    return btn


def _audio_extension(mime: str) -> str:
    normalized = str(mime or "").lower()
    if "wav" in normalized:
        return ".wav"
    if "mpeg" in normalized or "mp3" in normalized:
        return ".mp3"
    if "ogg" in normalized:
        return ".ogg"
    if "mp4" in normalized:
        return ".m4a"
    return ".wav"


def _send_btn(size: int = 36) -> QToolButton:
    """Send button — filled blue circle with arrow icon."""
    btn = QToolButton()
    btn.setIcon(get_icon(_ICON_SEND, _ICON_COLOR_SEND, 20))
    btn.setIconSize(QSize(20, 20))
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    btn.setToolTip("Send")
    btn.setObjectName("composer_send_btn")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(size, size)
    btn.setProperty("ui_role", "composer_send_icon_btn")
    return btn


class _ComposerTextEdit(QTextEdit):
    def __init__(self, on_mime_paste, on_geometry_changed=None, parent=None):
        super().__init__(parent)
        self._on_mime_paste = on_mime_paste
        self._on_geometry_changed = on_geometry_changed

    def insertFromMimeData(self, source: QMimeData):
        if callable(self._on_mime_paste):
            try:
                if self._on_mime_paste(source):
                    return
            except Exception:
                pass
        super().insertFromMimeData(source)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if callable(self._on_geometry_changed):
            try:
                self._on_geometry_changed()
            except Exception:
                pass


# ── PDF thumbnail helper ──────────────────────────────────────────────────────

def _pdf_thumbnail(path: str, size: int = 36) -> "QPixmap | None":
    """
    Render the first page of a PDF to a square QPixmap of `size` × `size`.
    Returns None if pypdfium2 is not installed or the file cannot be opened.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    try:
        doc  = pdfium.PdfDocument(path)
        page = doc[0]
        # Scale so the longest dimension = size*3 (render at 3× for crispness)
        w, h  = page.get_width(), page.get_height()
        scale = (size * 3) / max(w, h)
        bitmap = page.render(scale=scale, rotation=0)
        pil_img = bitmap.to_pil()

        # Convert PIL → QPixmap via raw bytes
        from PySide6.QtGui import QImage
        pil_img = pil_img.convert("RGBA")
        data = pil_img.tobytes("raw", "RGBA")
        qimage = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888)
        pix = QPixmap.fromImage(qimage).scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Centre-crop to square
        src = min(pix.width(), pix.height())
        pix = pix.copy((pix.width() - src) // 2, (pix.height() - src) // 2, src, src)
        doc.close()
        return pix
    except Exception:
        return None


# ── File attachment chip ───────────────────────────────────────────────────────

def _attach_chip(path: str, on_remove) -> QFrame:
    """
    Small chip showing an attached file with thumbnail (images) or
    a file-type icon (other files), plus an ✕ to remove it.
    """
    chip = QFrame()
    chip.setFixedHeight(52)
    chip.setProperty("ui_role", "composer_attach_chip")
    row = QHBoxLayout(chip)
    row.setContentsMargins(8, 6, 6, 6)
    row.setSpacing(8)

    # Thumbnail or type icon
    preview = QLabel()
    preview.setFixedSize(36, 36)
    preview.setProperty("ui_role", "composer_attach_thumb")
    preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
    mime, _ = mimetypes.guess_type(path)

    if mime and mime.startswith("image/"):
        pix = QPixmap(path).scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation)
        src_size = min(pix.width(), pix.height())
        pix = pix.copy((pix.width() - src_size) // 2, (pix.height() - src_size) // 2, src_size, src_size)
        preview.setPixmap(pix)

    elif mime == "application/pdf" or path.lower().endswith(".pdf"):
        pix = _pdf_thumbnail(path, 36)
        if pix:
            preview.setPixmap(pix)
        else:
            preview.setText("PDF")
            preview.setProperty("ui_role", "composer_attach_ext")

    else:
        ext = os.path.splitext(path)[1].upper().lstrip(".") or "FILE"
        preview.setText(ext[:4])
        preview.setProperty("ui_role", "composer_attach_ext")


    row.addWidget(preview)

    name_col = QVBoxLayout()
    name_col.setSpacing(2)
    name_lbl = QLabel(os.path.basename(path))
    name_lbl.setProperty("ui_role", "composer_attach_name")
    name_lbl.setMaximumWidth(140)
    try:
        size_bytes = os.path.getsize(path)
        size_str = f"{size_bytes / 1024:.0f} KB" if size_bytes < 1024 * 1024 else f"{size_bytes / (1024*1024):.1f} MB"
    except OSError:
        size_str = ""
    size_lbl = QLabel(size_str)
    size_lbl.setProperty("ui_role", "composer_attach_size")
    name_col.addWidget(name_lbl)
    name_col.addWidget(size_lbl)
    row.addLayout(name_col)

    rm_btn = QToolButton()
    rm_btn.setIcon(get_icon("ric.close-line", "#71717a", 12))
    rm_btn.setIconSize(QSize(12, 12))
    rm_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    rm_btn.setFixedSize(18, 18)
    rm_btn.setProperty("ui_role", "composer_attach_remove")
    rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    rm_btn.clicked.connect(lambda: on_remove(chip))
    row.addStretch()
    row.addWidget(rm_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

    return chip


def _normalize_capabilities(raw: Any) -> list[str]:
    capabilities: list[str] = []
    if not isinstance(raw, list):
        return capabilities
    for item in raw:
        value = str(item or "").strip()
        if value:
            capabilities.append(value)
    return capabilities


def _render_capability_badges(container: QFrame, capabilities: list[str]) -> None:
    layout = container.layout()
    if layout is None:
        return
    while layout.count():
        child = layout.takeAt(0)
        child_widget = child.widget() if child is not None else None
        if child_widget is not None:
            child_widget.setParent(None)
            child_widget.deleteLater()

    for capability in capabilities:
        chip = QLabel(capability)
        chip.setProperty("ui_role", "composer_capability_badge")
        layout.addWidget(chip)

    layout.addStretch()
    container.setProperty("model_capabilities", list(capabilities))
    container.setVisible(bool(capabilities))


# ── ComposerRenderer ──────────────────────────────────────────────────────────

class ComposerRenderer(BaseRenderer):
    component_type = "Composer"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "value": self.PROPERTY,
            "placeholder": self.PROPERTY,
            "disabled": self.PROPERTY,
            "model": self.PROPERTY,
            "model_capabilities": self.PROPERTY,
            "options": self.COMPONENT,
            "options_schema": self.COMPONENT,
            "options_editable": self.COMPONENT,
            "current_request": self.PROPERTY,
            "multiline": self.COMPONENT,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        outer = QFrame()
        outer.setObjectName(comp_id)
        outer.setProperty("ui_role", "composer_outer")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ── Unified card (border wraps both strip + input) ─────────────────────
        card = QFrame()
        card.setProperty("ui_role", "advanced_composer")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # ── Attachment strip (inside card, hidden when empty) ──────────────────
        attach_strip = QFrame()
        attach_strip.setProperty("ui_role", "composer_attach_strip")
        attach_layout = QHBoxLayout(attach_strip)
        attach_layout.setContentsMargins(12, 10, 12, 10)
        attach_layout.setSpacing(8)
        attach_layout.addStretch()
        attach_strip.setVisible(False)
        attach_strip._chips: List[str] = []  # type: ignore[attr-defined]

        def _remove_chip(chip_widget):
            path = chip_widget.property("attach_path") or ""
            if path in attach_strip._chips:
                attach_strip._chips.remove(path)
            attach_layout.removeWidget(chip_widget)
            chip_widget.setParent(None)
            chip_widget.deleteLater()
            if not attach_strip._chips:
                attach_strip.setVisible(False)

        def _add_attachment_chip(path: str) -> bool:
            if not path or not os.path.isfile(path) or path in attach_strip._chips:
                return False
            chip = _attach_chip(path, _request_remove_attachment_chip)
            chip.setProperty("attach_path", path)
            attach_strip._chips.append(path)
            attach_layout.insertWidget(attach_layout.count() - 1, chip)
            attach_strip.setVisible(True)
            return True

        def _paste_image_paths_from_mime(mime_data: QMimeData) -> list[str]:
            image_paths: list[str] = []
            if mime_data is None:
                return image_paths
            if mime_data.hasUrls():
                for url in mime_data.urls():
                    if not url.isLocalFile():
                        continue
                    path = url.toLocalFile()
                    guessed_mime, _ = mimetypes.guess_type(path)
                    if guessed_mime and guessed_mime.startswith("image/"):
                        image_paths.append(path)
            if image_paths:
                return image_paths
            if mime_data.hasImage():
                image = mime_data.imageData()
                qimage = image if isinstance(image, QImage) else QImage(image)
                if not qimage.isNull():
                    fd, temp_path = tempfile.mkstemp(prefix="composer_clip_", suffix=".png")
                    os.close(fd)
                    if qimage.save(temp_path, "PNG"):
                        image_paths.append(temp_path)
                    else:
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
            return image_paths

        def _handle_mime_paste(mime_data: QMimeData) -> bool:
            if not attachment_enabled:
                return False
            added = False
            for image_path in _paste_image_paths_from_mime(mime_data):
                added = _add_attachment_chip(image_path) or added
            return added

        def _attachment_paths() -> list[str]:
            return [str(path) for path in list(getattr(attach_strip, "_chips", [])) if str(path).strip()]

        def _attachment_preview_payloads() -> list[dict[str, Any]]:
            payloads: list[dict[str, Any]] = []
            for path in _attachment_paths():
                file_path = str(path or "").strip()
                if not file_path:
                    continue
                mime, _ = mimetypes.guess_type(file_path)
                try:
                    size = os.path.getsize(file_path)
                except OSError:
                    size = 0
                payloads.append(
                    {
                        "name": os.path.basename(file_path),
                        "size": size,
                        "type": mime or "application/octet-stream",
                    }
                )
            return payloads

        def _upload_attachments(action_def: dict[str, Any]) -> list[dict[str, Any]] | None:
            uploaded: list[dict[str, Any]] = []
            module_name = _infer_module_name({"action": action_def}, app_instance)
            for local_path in _attachment_paths():
                if not local_path:
                    continue
                row = _upload_file_to_media_storage(
                    local_path=local_path,
                    module_name=module_name,
                    ingest=bool(props.get("ingest", True)),
                    action_name=str(action_def.get("name") or "").strip(),
                    app_instance=app_instance,
                )
                if row is None:
                    return None
                uploaded.append(row)
            return uploaded

        def _clear_attachments() -> None:
            for path in list(_attachment_paths()):
                for idx in range(attach_layout.count()):
                    child = attach_layout.itemAt(idx)
                    chip_widget = child.widget() if child is not None else None
                    if chip_widget is None:
                        continue
                    if str(chip_widget.property("attach_path") or "") == path:
                        _remove_chip(chip_widget)
                        break

        card_layout.addWidget(attach_strip)

        # Thin divider shown only when strip is visible
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setProperty("ui_role", "composer_inner_divider")
        divider.setVisible(False)
        card_layout.addWidget(divider)

        # Keep divider in sync with strip visibility
        _orig_set_visible = attach_strip.setVisible
        def _set_strip_visible(v: bool):
            _orig_set_visible(v)
            divider.setVisible(v)
        attach_strip.setVisible = _set_strip_visible  # type: ignore[method-assign]

        # ── Input area ────────────────────────────────────────────────────────
        input_area = QFrame()
        input_area.setProperty("ui_role", "composer_input_area")
        input_area_layout = QVBoxLayout(input_area)
        input_area_layout.setContentsMargins(12, 10, 12, 10)
        input_area_layout.setSpacing(8)
        card_layout.addWidget(input_area)

        capabilities = _normalize_capabilities(props.get("model_capabilities") or [])
        current_request = str(props.get("current_request") or "").strip()
        running = bool(current_request)
        show_capabilities = bool(props.get("show_capabilities", True))
        outer.setProperty("current_request", current_request)

        caps_row = QFrame()
        caps_row.setObjectName(f"{comp_id}__caps")
        caps_row.setProperty("ui_role", "composer_capabilities_row")
        caps_layout = QHBoxLayout(caps_row)
        caps_layout.setContentsMargins(0, 0, 0, 0)
        caps_layout.setSpacing(6)
        _render_capability_badges(caps_row, capabilities if show_capabilities else [])
        caps_row.setVisible(show_capabilities and bool(capabilities))
        input_area_layout.addWidget(caps_row)

        # Text input
        multiline = bool(props.get("multiline", True))

        input_box = _ComposerTextEdit(_handle_mime_paste)
        input_box.setObjectName(f"{comp_id}__input")
        input_box.setPlaceholderText(str(props.get("placeholder", "Send a message…")))
        input_box.setPlainText(str(props.get("value", "")))
        input_box.setFixedHeight(44 if not multiline else 80)
        input_box.setDisabled(bool(props.get("disabled", False)) or running)
        input_box.setProperty("ui_role", "advanced_composer_input")
        input_box.setFrameShape(QFrame.Shape.NoFrame)

        def _resize_input_to_content():
            if not multiline:
                return
            min_height = 44
            max_height = 220
            doc_height = int(input_box.document().size().height())
            extra = int(input_box.document().documentMargin() * 2) + 12
            new_height = max(min_height, min(max_height, doc_height + extra))
            input_box.setFixedHeight(new_height)
            if new_height >= max_height:
                input_box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            else:
                input_box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        input_box._on_geometry_changed = _resize_input_to_content  # type: ignore[attr-defined]

        publish_bound_value(app_instance, outer, comp_id, input_box.toPlainText())
        input_box.textChanged.connect(
            lambda: publish_bound_value(app_instance, input_box, comp_id, input_box.toPlainText())
        )
        input_box.textChanged.connect(_resize_input_to_content)
        _resize_input_to_content()
        input_area_layout.addWidget(input_box)

        # ── Bottom toolbar ────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(4)
        toolbar.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        def _normalize_action_def(raw: Any) -> Dict[str, Any]:
            if isinstance(raw, dict):
                return {
                    "name": str(raw.get("name") or "").strip(),
                    "context": dict(raw.get("context") or {}),
                    "confirm": raw.get("confirm"),
                }
            if isinstance(raw, str):
                return {"name": raw.strip(), "context": {}, "confirm": None}
            return {"name": "", "context": {}, "confirm": None}

        def _normalize_named_options(raw: Any) -> list[dict[str, str]]:
            normalized: list[dict[str, str]] = []
            if not isinstance(raw, list):
                return normalized
            for item in raw:
                if isinstance(item, dict):
                    value = str(item.get("id") or item.get("value") or "").strip()
                    label = str(item.get("name") or item.get("label") or value).strip()
                else:
                    value = str(item or "").strip()
                    label = value
                if not value:
                    continue
                normalized.append({"id": value, "name": label})
            return normalized

        def _normalize_simple_options(raw: Any) -> list[str]:
            values: list[str] = []
            if not isinstance(raw, list):
                return values
            for item in raw:
                if isinstance(item, dict):
                    value = str(item.get("id") or item.get("name") or item.get("value") or item.get("label") or "").strip()
                else:
                    value = str(item or "").strip()
                if value:
                    values.append(value)
            return values

        submit_def = _normalize_action_def(props.get("on_submit") or props.get("send_action"))
        stop_def = _normalize_action_def(props.get("on_stop") or props.get("on_stop_enabled") or props.get("cancel_action"))
        interaction_def = _normalize_action_def(props.get("action"))
        voice_def = _normalize_action_def(props.get("voice_action"))

        voice_enabled = bool(props.get("voice", True))
        attachment_enabled = bool(props.get("enable_attachment", True))
        attachment_accept = str(props.get("attachment_accept") or "").strip()
        stop_enabled = bool(props.get("stop_enabled", bool(stop_def.get("name")) or running))
        model_editable = bool(props.get("model_editable", True))
        tools_editable = bool(props.get("tools_editable", True))
        skills_editable = bool(props.get("skills_editable", True))
        mcp_editable = bool(props.get("mcp_editable", True))
        options_editable = bool(props.get("options_editable", False))
        options = dict(props.get("options") or {}) if isinstance(props.get("options"), dict) else {}
        options_schema = props.get("options_schema") if isinstance(props.get("options_schema"), dict) else {}
        option_fields = list(options_schema.get("fields") or []) if isinstance(options_schema, dict) else []
        option_field_names = {
            str(field.get("name") or "").strip()
            for field in option_fields
            if isinstance(field, dict) and str(field.get("name") or "").strip()
        }

        def _option_value(name: str) -> Any:
            return current_options.get(str(name or "").strip())

        def _set_option_value(name: str, value: Any) -> None:
            key = str(name or "").strip()
            if not key:
                return
            if value == "":
                current_options.pop(key, None)
            else:
                current_options[key] = value

        def _parse_option_value(field: dict[str, Any], value: str) -> Any:
            raw_type = str(field.get("type") or "").lower()
            if raw_type in {"boolean", "bool", "checkbox"} or isinstance(field.get("value"), bool):
                return value == "true"
            if raw_type == "integer":
                try:
                    return int(value)
                except ValueError:
                    return value
            if raw_type == "number":
                try:
                    return float(value)
                except ValueError:
                    return value
            return value

        model_options = _normalize_named_options(props.get("models"))
        tool_options = _normalize_named_options(props.get("tools"))
        skill_options = _normalize_named_options(props.get("skills"))
        mcp_options = _normalize_named_options(props.get("mcp"))

        selected_model = str(props.get("model") or "").strip()
        if not selected_model and model_options:
            selected_model = model_options[0]["id"]
        selected_tools = set(_normalize_simple_options(props.get("selected_tools")))
        selected_skills = set(_normalize_simple_options(props.get("selected_skills")))
        selected_mcp = set(_normalize_simple_options(props.get("selected_mcp")))
        current_options = dict(options)
        for raw_field in option_fields:
            if not isinstance(raw_field, dict):
                continue
            name = str(raw_field.get("name") or "").strip()
            if (
                name
                and name not in current_options
                and raw_field.get("value") is not None
            ):
                current_options[name] = raw_field.get("value")
        model_combo: QComboBox | None = None
        settings_menu: QMenu | None = None

        def _option_entries() -> list[dict[str, Any]]:
            return [
                {"key": key, "value": value}
                for key, value in current_options.items()
                if key in option_field_names
            ]

        def _current_model() -> str:
            if model_combo is not None and model_combo.currentIndex() >= 0:
                return str(model_combo.currentData() or "")
            return selected_model

        def _confirm_action_def(action_def: dict[str, Any]) -> bool:
            return confirm_action(app_instance, action_def.get("confirm"))

        def _emit_action_def(action_def: dict[str, Any], payload: dict[str, Any]) -> None:
            action_name = str(action_def.get("name") or "").strip()
            if not action_name:
                return
            emit_action(
                app_instance,
                action_name,
                {
                    **dict(action_def.get("context") or {}),
                    **payload,
                },
                surface_id,
                comp_id,
            )

        def _interaction_payload(intent: str, **extra: Any) -> dict[str, Any]:
            return {
                "intent": intent,
                "component_id": comp_id,
                "value": input_box.toPlainText(),
                "model": _current_model(),
                "selected_tools": sorted(selected_tools),
                "selected_skills": sorted(selected_skills),
                "selected_mcp": sorted(selected_mcp),
                "model_capabilities": list(caps_row.property("model_capabilities") or []),
                "options": _option_entries(),
                "current_request": str(outer.property("current_request") or ""),
                **extra,
            }

        def _emit_interaction(intent: str, **extra: Any) -> None:
            action_name = str(interaction_def.get("name") or "").strip()
            if not action_name:
                return
            if not _confirm_action_def(interaction_def):
                return
            _emit_action_def(
                interaction_def,
                {comp_id: _interaction_payload(intent, **extra)},
            )

        def _request_remove_attachment_chip(chip_widget) -> None:
            if interaction_def.get("name") and not _confirm_action_def(interaction_def):
                return
            _remove_chip(chip_widget)
            if interaction_def.get("name"):
                _emit_action_def(
                    interaction_def,
                    {comp_id: _interaction_payload("attachment_remove", attachments=_attachment_preview_payloads())},
                )

        # Left icons: attach file + audio
        attach_btn = _icon_btn(_ICON_ATTACH, "Attach file",  "composer_attach_btn")
        audio_btn  = _icon_btn(_ICON_MIC,    "Record audio", "composer_audio_btn")
        if attachment_enabled:
            toolbar.addWidget(attach_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        if voice_enabled:
            toolbar.addWidget(audio_btn,  0, Qt.AlignmentFlag.AlignVCenter)

        if model_options:
            model_combo = QComboBox()
            model_combo.setObjectName(f"{comp_id}__model")
            model_combo.setProperty("ui_role", "composer_model_select")
            for entry in model_options:
                model_combo.addItem(entry["name"], entry["id"])
            if selected_model:
                selected_index = model_combo.findData(selected_model)
                if selected_index >= 0:
                    model_combo.setCurrentIndex(selected_index)
            model_combo.currentIndexChanged.connect(
                lambda idx: _emit_interaction(
                    "model_change",
                    model=model_combo.itemData(idx) if idx >= 0 else "",
                    model_name=model_combo.currentText(),
                )
            )
            model_combo.setEnabled(not running and model_editable and not bool(props.get("disabled", False)))
            toolbar.addWidget(model_combo, 0, Qt.AlignmentFlag.AlignVCenter)

        if tool_options or skill_options or mcp_options or (options_editable and option_fields):
            settings_btn = _icon_btn(_ICON_SETTINGS, "Tools, skills & MCP", "composer_settings_btn")
            settings_btn.setProperty("ui_role", "composer_settings_btn")
            settings_menu = QMenu(settings_btn)
            settings_menu.setProperty("ui_role", "composer_settings_menu")
            settings_menu.setStyleSheet(
                """
                QMenu[ui_role="composer_settings_menu"] {
                    background: #111113;
                    border: 1px solid #27272a;
                    border-radius: 8px;
                    padding: 6px;
                }
                QMenu[ui_role="composer_settings_menu"]::item {
                    padding: 6px 10px;
                }
                QLabel[ui_role="composer_option_key"] {
                    color: #a1a1aa;
                    font-size: 12px;
                    font-family: monospace;
                }
                QLineEdit[ui_role="composer_option_input"],
                QComboBox[ui_role="composer_option_input"] {
                    background: #09090b;
                    border: 1px solid #27272a;
                    border-radius: 4px;
                    color: #fafafa;
                    font-size: 12px;
                    padding: 2px 8px;
                }
                QLineEdit[ui_role="composer_option_input"]:focus,
                QComboBox[ui_role="composer_option_input"]:focus {
                    border: 1px solid #52525b;
                }
                """
            )

            def _rebuild_settings_menu() -> None:
                if settings_menu is None:
                    return
                settings_menu.clear()

                if options_editable and option_fields:
                    options_title = QAction("Options", settings_menu)
                    options_title.setEnabled(False)
                    settings_menu.addAction(options_title)
                    for raw_field in option_fields:
                        if not isinstance(raw_field, dict):
                            continue
                        name = str(raw_field.get("name") or "").strip()
                        if not name:
                            continue
                        row = QFrame()
                        row_layout = QHBoxLayout(row)
                        row_layout.setContentsMargins(8, 2, 8, 2)
                        row_layout.setSpacing(8)
                        label = QLabel(str(raw_field.get("label") or name))
                        label.setProperty("ui_role", "composer_option_key")
                        label.setFixedWidth(116)
                        row_layout.addWidget(label)
                        choices = list(raw_field.get("options") or []) if isinstance(raw_field.get("options"), list) else []
                        is_boolean = str(raw_field.get("type") or "").lower() in {"boolean", "bool", "checkbox"} or isinstance(_option_value(name), bool)
                        if is_boolean or choices:
                            combo = QComboBox()
                            combo.setFixedSize(104, 26)
                            combo.setProperty("ui_role", "composer_option_input")
                            values = choices or [
                                {"label": "true", "value": True},
                                {"label": "false", "value": False},
                            ]
                            current_value = _option_value(name)
                            selected_index = 0
                            for index, raw_choice in enumerate(values):
                                if isinstance(raw_choice, dict):
                                    choice_value = raw_choice.get("value")
                                    choice_label = raw_choice.get("label", choice_value)
                                else:
                                    choice_value = raw_choice
                                    choice_label = raw_choice
                                combo.addItem(str(choice_label), "true" if choice_value is True else "false" if choice_value is False else str(choice_value))
                                if choice_value == current_value:
                                    selected_index = index
                            combo.setCurrentIndex(selected_index)

                            def _update_combo(index: int, current=name, field=raw_field, widget=combo) -> None:
                                _set_option_value(current, _parse_option_value(field, str(widget.itemData(index))))

                            combo.currentIndexChanged.connect(_update_combo)
                            row_layout.addWidget(combo)
                        elif str(raw_field.get("type") or "").lower() == "integer":
                            line = QLineEdit()
                            line.setFixedSize(104, 26)
                            line.setProperty("ui_role", "composer_option_input")
                            min_value = raw_field.get("min")
                            max_value = raw_field.get("max")
                            line.setValidator(
                                QIntValidator(
                                    int(min_value) if min_value is not None else -2147483648,
                                    int(max_value) if max_value is not None else 2147483647,
                                    line,
                                )
                            )
                            value = _option_value(name)
                            if value is not None:
                                line.setText(str(value))

                            def _update_integer_option(value: str, current=name, widget=line) -> None:
                                if value == "":
                                    _set_option_value(current, "")
                                elif widget.hasAcceptableInput():
                                    _set_option_value(current, int(value))

                            line.textChanged.connect(_update_integer_option)
                            row_layout.addWidget(line)
                        elif str(raw_field.get("type") or "").lower() == "number":
                            line = QLineEdit()
                            line.setFixedSize(104, 26)
                            line.setProperty("ui_role", "composer_option_input")
                            locale = QLocale()
                            min_value = raw_field.get("min")
                            max_value = raw_field.get("max")
                            validator = QDoubleValidator(
                                float(min_value) if min_value is not None else -1000000000000,
                                float(max_value) if max_value is not None else 1000000000000,
                                int(raw_field.get("decimals", 6)),
                                line,
                            )
                            validator.setLocale(locale)
                            line.setValidator(validator)
                            value = _option_value(name)
                            if value is not None:
                                line.setText(locale.toString(float(value)))

                            def _update_number_option(
                                value: str,
                                current=name,
                                widget=line,
                                number_locale=locale,
                            ) -> None:
                                if value == "":
                                    _set_option_value(current, "")
                                elif widget.hasAcceptableInput():
                                    parsed, ok = number_locale.toDouble(value)
                                    if ok:
                                        _set_option_value(current, parsed)

                            line.textChanged.connect(_update_number_option)
                            row_layout.addWidget(line)
                        else:
                            line = QLineEdit()
                            line.setFixedSize(104, 26)
                            line.setProperty("ui_role", "composer_option_input")
                            value = _option_value(name)
                            line.setText("" if value is None else str(value))
                            line.setPlaceholderText("value")

                            def _update_option(value: str, current=name, field=raw_field) -> None:
                                _set_option_value(current, "" if value == "" else _parse_option_value(field, value))

                            line.textChanged.connect(_update_option)
                            row_layout.addWidget(line)
                        row.setFixedHeight(32)
                        action_item = QWidgetAction(settings_menu)
                        action_item.setDefaultWidget(row)
                        settings_menu.addAction(action_item)
                    if (tools_editable and tool_options) or (skills_editable and skill_options) or (mcp_editable and mcp_options):
                        settings_menu.addSeparator()

                if tools_editable and tool_options:
                    tools_menu = settings_menu.addMenu("Tools")
                    for entry in tool_options:
                        value = entry["id"]
                        action_item = QAction(entry["name"], tools_menu)
                        action_item.setCheckable(True)
                        action_item.setChecked(value in selected_tools)
                        action_item.toggled.connect(
                            lambda checked, current=value: (
                                selected_tools.add(current) if checked else selected_tools.discard(current),
                                _emit_interaction(
                                    "tools_change",
                                    selected_tools=sorted(selected_tools),
                                    selected_skills=sorted(selected_skills),
                                    selected_mcp=sorted(selected_mcp),
                                ),
                            )
                        )
                        tools_menu.addAction(action_item)

                if skills_editable and skill_options:
                    skills_menu = settings_menu.addMenu("Skills")
                    for entry in skill_options:
                        value = entry["id"]
                        action_item = QAction(entry["name"], skills_menu)
                        action_item.setCheckable(True)
                        action_item.setChecked(value in selected_skills)
                        action_item.toggled.connect(
                            lambda checked, current=value: (
                                selected_skills.add(current) if checked else selected_skills.discard(current),
                                _emit_interaction(
                                    "skills_change",
                                    selected_tools=sorted(selected_tools),
                                    selected_skills=sorted(selected_skills),
                                    selected_mcp=sorted(selected_mcp),
                                ),
                            )
                        )
                        skills_menu.addAction(action_item)

                if mcp_editable and mcp_options:
                    mcp_menu = settings_menu.addMenu("MCP")
                    for entry in mcp_options:
                        value = entry["id"]
                        action_item = QAction(entry["name"], mcp_menu)
                        action_item.setCheckable(True)
                        action_item.setChecked(value in selected_mcp)
                        action_item.toggled.connect(
                            lambda checked, current=value: (
                                selected_mcp.add(current) if checked else selected_mcp.discard(current),
                                _emit_interaction(
                                    "mcp_change",
                                    selected_tools=sorted(selected_tools),
                                    selected_skills=sorted(selected_skills),
                                    selected_mcp=sorted(selected_mcp),
                                ),
                            )
                        )
                        mcp_menu.addAction(action_item)

                if not (options_editable and option_fields) and not (tools_editable and tool_options) and not (skills_editable and skill_options) and not (mcp_editable and mcp_options):
                    empty = QAction("No options", settings_menu)
                    empty.setEnabled(False)
                    settings_menu.addAction(empty)

            _rebuild_settings_menu()
            settings_btn.setMenu(settings_menu)
            settings_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            settings_btn.setDisabled(running or bool(props.get("disabled", False)))
            toolbar.addWidget(settings_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        toolbar.addStretch()

        # Right: Stop (driven by explicit stop props) + Send
        if stop_enabled and stop_def.get("name"):
            stop_btn = _icon_btn(_ICON_STOP, "Stop generation", "composer_stop_btn", size=32)
            stop_btn.setProperty("ui_role", "composer_stop_icon_btn")
            stop_btn.setDisabled(not running)
            stop_btn.clicked.connect(
                lambda: (
                    _emit_action_def(
                        stop_def,
                        {
                            comp_id: {
                                "intent": "stop",
                                "component_id": comp_id,
                                "value": input_box.toPlainText(),
                                "text": input_box.toPlainText(),
                                "current_request": str(outer.property("current_request") or ""),
                                "model": _current_model(),
                                "selected_tools": sorted(selected_tools),
                                "selected_skills": sorted(selected_skills),
                                "selected_mcp": sorted(selected_mcp),
                                "model_capabilities": list(caps_row.property("model_capabilities") or []),
                                "options": _option_entries(),
                            }
                        },
                    )
                    if _confirm_action_def(stop_def)
                    else None
                )
            )
            toolbar.addWidget(stop_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        def _emit_send_action() -> None:
            if not submit_def.get("name"):
                return
            if not _confirm_action_def(submit_def):
                return
            attachments = _upload_attachments(submit_def)
            if attachments is None:
                return
            composer_payload = {
                "intent": "submit",
                "component_id": comp_id,
                "text": input_box.toPlainText(),
                "attachments": attachments,
                "options": _option_entries(),
                "selected_tools": sorted(selected_tools),
                "selected_skills": sorted(selected_skills),
                "selected_mcp": sorted(selected_mcp),
            }
            _emit_action_def(
                submit_def,
                {
                    comp_id: composer_payload,
                },
            )
            _clear_attachments()

        _original_key_press = input_box.keyPressEvent

        def _handle_key_press(event):
            key = event.key()
            modifiers = event.modifiers()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                modifiers & Qt.KeyboardModifier.ShiftModifier
            ):
                _emit_send_action()
                event.accept()
                return
            _original_key_press(event)

        input_box.keyPressEvent = _handle_key_press  # type: ignore[method-assign]

        send_btn = _send_btn()
        send_btn.setDisabled(running or bool(props.get("disabled", False)))
        if submit_def.get("name"):
            send_btn.clicked.connect(_emit_send_action)
        toolbar.addWidget(send_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        input_area_layout.addLayout(toolbar)

        # ── File attach logic ─────────────────────────────────────────────────
        def _open_file_dialog():
            if not attachment_enabled:
                return
            if interaction_def.get("name") and not _confirm_action_def(interaction_def):
                return
            from PySide6.QtWidgets import QFileDialog
            paths, _ = QFileDialog.getOpenFileNames(
                outer,
                "Attach files",
                "",
                _file_dialog_filter(attachment_accept),
            )
            added_count = 0
            for path in paths:
                if _add_attachment_chip(path):
                    added_count += 1
            if added_count:
                _emit_action_def(
                    interaction_def,
                    {comp_id: _interaction_payload("attachment_add", added=added_count, attachments=_attachment_preview_payloads())},
                )

        if attachment_enabled:
            attach_btn.setDisabled(running or bool(props.get("disabled", False)))
            attach_btn.clicked.connect(_open_file_dialog)

        audio_state: dict[str, Any] = {
            "recording": False,
            "stopping": False,
            "started_at": 0.0,
            "local_path": "",
        }

        def _set_audio_recording(active: bool) -> None:
            audio_state["recording"] = bool(active)
            if active:
                audio_btn.setIcon(get_icon(_ICON_MIC_ON, _ICON_COLOR_DANGER, 18))
                audio_btn.setProperty("ui_role", "composer_audio_btn_active")
            else:
                audio_btn.setIcon(get_icon(_ICON_MIC, _ICON_COLOR_MUTED, 18))
                audio_btn.setProperty("ui_role", "composer_icon_btn")
            audio_btn.style().unpolish(audio_btn)
            audio_btn.style().polish(audio_btn)

        def _emit_voice_toggle(active: bool) -> None:
            if interaction_def.get("name"):
                _emit_action_def(
                    interaction_def,
                    {comp_id: _interaction_payload("voice_toggle", voice_active=active)},
                )

        def _transcribe_recording(local_path: str) -> None:
            if not voice_def.get("name"):
                return
            uploaded = _upload_file_to_media_storage(
                local_path=local_path,
                module_name=_infer_module_name({"action": voice_def}, app_instance),
                ingest=False,
                action_name=str(voice_def.get("name") or "").strip(),
                app_instance=app_instance,
            )
            if uploaded is None:
                return
            emit_action_spec(
                app_instance,
                voice_def,
                {
                    comp_id: _interaction_payload(
                        "voice_transcribe",
                        audio=uploaded,
                        target=comp_id,
                    )
                },
                surface_id,
                comp_id,
            )

        def _on_audio_stopped() -> None:
            if not audio_state.get("stopping"):
                return
            audio_state["stopping"] = False
            _set_audio_recording(False)
            local_path = str(audio_state.get("local_path") or "")
            if not local_path or not os.path.isfile(local_path) or os.path.getsize(local_path) <= 0:
                return
            _transcribe_recording(local_path)

        def _ensure_audio_recorder() -> bool:
            if audio_state.get("recorder") is not None:
                return True
            try:
                from PySide6.QtMultimedia import (
                    QAudioInput,
                    QMediaCaptureSession,
                    QMediaDevices,
                    QMediaFormat,
                    QMediaRecorder,
                )
            except Exception:
                return False
            audio_input = QAudioInput(QMediaDevices.defaultAudioInput(), outer)
            capture_session = QMediaCaptureSession(outer)
            recorder = QMediaRecorder(outer)
            capture_session.setAudioInput(audio_input)
            capture_session.setRecorder(recorder)
            media_format = QMediaFormat()
            media_format.setFileFormat(QMediaFormat.FileFormat.Wave)
            media_format.setAudioCodec(QMediaFormat.AudioCodec.Wave)
            recorder.setMediaFormat(media_format)
            recorder.recorderStateChanged.connect(
                lambda state_value: _on_audio_stopped()
                if state_value == QMediaRecorder.RecorderState.StoppedState
                else None
            )
            audio_state["audio_input"] = audio_input
            audio_state["capture_session"] = capture_session
            audio_state["recorder"] = recorder
            return True

        def _start_audio() -> None:
            if not _ensure_audio_recorder():
                return
            recorder = audio_state.get("recorder")
            if recorder is None:
                return
            suffix = _audio_extension(str(recorder.mediaFormat().mimeType().name()))
            target = tempfile.NamedTemporaryFile(
                prefix="composer_recording_",
                suffix=suffix,
                delete=False,
            )
            target.close()
            audio_state["local_path"] = target.name
            audio_state["started_at"] = time.monotonic()
            recorder.setOutputLocation(QUrl.fromLocalFile(target.name))
            recorder.record()
            _set_audio_recording(True)
            _emit_voice_toggle(True)

        def _stop_audio() -> None:
            recorder = audio_state.get("recorder")
            if recorder is None:
                return
            audio_state["stopping"] = True
            recorder.stop()
            _emit_voice_toggle(False)

        def _toggle_audio():
            if interaction_def.get("name") and not _confirm_action_def(interaction_def):
                return
            if audio_state.get("recording"):
                _stop_audio()
            else:
                _start_audio()

        if voice_enabled:
            audio_btn.setDisabled(running or bool(props.get("disabled", False)))
            audio_btn.clicked.connect(_toggle_audio)

        outer_layout.addWidget(card)
        return outer

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        input_box = widget.findChild(QTextEdit, f"{widget.objectName()}__input")
        if input_box is None:
            super().update_widget_property(widget, prop, value)
            return
        if prop == "model":
            model_combo = widget.findChild(QComboBox, f"{widget.objectName()}__model")
            if model_combo is not None:
                selected = str(value or "").strip()
                if selected:
                    selected_index = model_combo.findData(selected)
                    if selected_index >= 0:
                        model_combo.setCurrentIndex(selected_index)
            return
        if prop == "model_capabilities":
            caps_row = widget.findChild(QFrame, f"{widget.objectName()}__caps")
            if caps_row is not None:
                _render_capability_badges(caps_row, _normalize_capabilities(value))
            return
        if prop == "current_request":
            current_request = str(value or "").strip()
            running = bool(current_request)
            widget.setProperty("current_request", current_request)
            input_box.setDisabled(running)
            send_btn = widget.findChild(QToolButton, "composer_send_btn")
            if send_btn is not None:
                send_btn.setDisabled(running)
            stop_btn = widget.findChild(QToolButton, "composer_stop_btn")
            if stop_btn is not None:
                stop_btn.setDisabled(not running)
            for object_name in ("composer_attach_btn", "composer_audio_btn", "composer_settings_btn"):
                button = widget.findChild(QToolButton, object_name)
                if button is not None:
                    button.setDisabled(running)
            return
        if prop == "value":
            text = "" if value is None else str(value)
            if input_box.toPlainText() != text:
                input_box.setPlainText(text)
            return
        if prop == "placeholder":
            input_box.setPlaceholderText("" if value is None else str(value))
            return
        if prop == "disabled":
            input_box.setDisabled(bool(value))
            return
        super().update_widget_property(widget, prop, value)
