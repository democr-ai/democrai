from __future__ import annotations
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFileDialog,
    QFrame,
    QToolButton,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap
from ...base import (
    BaseRenderer,
    confirm_action,
    emit_action_spec,
    publish_bound_value,
)
from ...icon import get_icon

_ATTACHMENT_TILE_SIZE = 96


class UploadTile(QFrame):
    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("hovered", "false")

    def _apply_hover(self, hovered: bool) -> None:
        self.setProperty("hovered", "true" if hovered else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def enterEvent(self, event):  # type: ignore[override]
        self._apply_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):  # type: ignore[override]
        self._apply_hover(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _upload_button_text(label_prop: Any) -> str:
    del label_prop
    return "Upload"


def _wrap_text(value: str, max_chars: int = 11, max_lines: int = 2) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Upload"
    words = raw.split()
    if not words:
        return raw

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) >= max_lines - 1:
            break
    if len(lines) < max_lines:
        lines.append(current)

    wrapped = lines[:max_lines]
    joined = " ".join(words)
    if "\n".join(wrapped).replace("\n", " ") != joined:
        wrapped[-1] = wrapped[-1][: max(0, max_chars - 1)].rstrip() + "…"
    return "\n".join(wrapped)


def _is_image_path(path: str) -> bool:
    ext = os.path.splitext(str(path or ""))[1].lower()
    return ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")


def _is_pdf_path(path: str) -> bool:
    return os.path.splitext(str(path or ""))[1].lower() == ".pdf"


def _runtime_token_holder(app_instance: Any) -> Any:
    current = app_instance
    visited = 0
    while current is not None and visited < 10:
        if hasattr(current, "jwt"):
            return current
        parent_getter = getattr(current, "parent", None)
        if callable(parent_getter):
            current = parent_getter()
        else:
            break
        visited += 1
    return app_instance


def _resolve_http_target(app_instance: Any) -> tuple[str, int]:
    current = app_instance
    visited = 0
    while current is not None and visited < 10:
        host = getattr(current, "host", None)
        port = getattr(current, "port", None)
        if host is not None or port is not None:
            return (str(host or "127.0.0.1"), int(port or 8000))
        parent_getter = getattr(current, "parent", None)
        if callable(parent_getter):
            current = parent_getter()
        else:
            break
        visited += 1
    return ("127.0.0.1", 8000)


def _infer_module_name(state_props: dict[str, Any], app_instance: Any) -> str:
    action = state_props.get("action")
    if isinstance(action, dict):
        action_name = str(action.get("name") or "").strip()
        if "." in action_name:
            prefix = str(action_name.split(".", 1)[0] or "").strip()
            if prefix:
                return prefix
    store = getattr(app_instance, "store", None)
    if store is not None and hasattr(store, "get"):
        try:
            current_path = str(store.get("/current_path", "", "global") or "").strip()
        except Exception:
            current_path = ""
        if current_path.startswith("/"):
            parts = [part for part in current_path.split("/") if part]
            if parts:
                return str(parts[0] or "core").strip() or "core"
    return "core"


def _build_upload_multipart(
    *,
    module_name: str,
    ingest: bool,
    filename: str,
    file_bytes: bytes,
    content_type: str,
    action_name: str | None = None,
) -> tuple[bytes, str]:
    boundary = f"----democrai-{uuid4().hex}"
    lines: list[bytes] = [
        f"--{boundary}\r\n".encode("utf-8"),
        b'Content-Disposition: form-data; name="module_name"\r\n\r\n',
        f"{module_name}\r\n".encode("utf-8"),
        f"--{boundary}\r\n".encode("utf-8"),
        b'Content-Disposition: form-data; name="ingest"\r\n\r\n',
        ("true\r\n" if ingest else "false\r\n").encode("utf-8"),
        f"--{boundary}\r\n".encode("utf-8"),
    ]
    normalized_action_name = str(action_name or "").strip()
    if normalized_action_name:
        lines.extend(
            [
                b'Content-Disposition: form-data; name="action_name"\r\n\r\n',
                f"{normalized_action_name}\r\n".encode("utf-8"),
                f"--{boundary}\r\n".encode("utf-8"),
            ]
        )
    lines.extend(
        [
            (
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            bytes(file_bytes or b""),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    payload = b"".join(lines)
    return payload, boundary


def _upload_file_to_media_storage(
    *,
    local_path: str,
    module_name: str,
    ingest: bool,
    action_name: str | None = None,
    app_instance: Any,
) -> dict[str, Any] | None:
    resolved = Path(str(local_path or "")).expanduser()
    if not resolved.exists() or not resolved.is_file():
        return None

    token_holder = _runtime_token_holder(app_instance)
    jwt = str(getattr(token_holder, "jwt", "") or "").strip()
    host, port = _resolve_http_target(app_instance)

    filename = str(resolved.name or "upload.bin")
    file_bytes = resolved.read_bytes()
    if not file_bytes:
        return None
    guessed_mime, _ = mimetypes.guess_type(filename)
    content_type = str(guessed_mime or "application/octet-stream")
    form_payload, boundary = _build_upload_multipart(
        module_name=module_name,
        ingest=bool(ingest),
        action_name=action_name,
        filename=filename,
        file_bytes=file_bytes,
        content_type=content_type,
    )
    request = urllib.request.Request(
        url=f"http://{host}:{port}/media/uploads/raw",
        method="POST",
        data=form_payload,
        headers={
            **({"X-JWT": jwt} if jwt else {}),
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=30.0
        ) as response:  # nosec B310 - local app endpoint
            raw = bytes(response.read() or b"")
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError:
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    if not isinstance(payload, dict):
        return None
    storage_path = str(payload.get("storage_path") or "").strip()
    if not storage_path:
        return None
    return {
        "name": filename,
        "path": storage_path,
        "storage_path": storage_path,
        "file_id": str(payload.get("file_id") or "").strip(),
        "type": str(payload.get("content_type") or content_type).strip(),
        "mime": str(payload.get("content_type") or content_type).strip(),
        "content_type": str(payload.get("content_type") or content_type).strip(),
        "size": int(payload.get("size_bytes") or len(file_bytes)),
        "size_bytes": int(payload.get("size_bytes") or len(file_bytes)),
        "extraction_request_id": str(payload.get("extraction_request_id") or "").strip()
        or None,
        "background_task_id": str(payload.get("background_task_id") or "").strip()
        or None,
    }


def build_local_attachment_entry(local_path: str) -> dict[str, Any] | None:
    resolved = Path(str(local_path or "")).expanduser()
    if not resolved.exists() or not resolved.is_file():
        return None
    filename = str(resolved.name or "upload.bin")
    guessed_mime, _ = mimetypes.guess_type(filename)
    return {
        "name": filename,
        "size": int(resolved.stat().st_size),
        "type": str(guessed_mime or "application/octet-stream"),
        "mime": str(guessed_mime or "application/octet-stream"),
        "local_path": str(resolved),
    }


def upload_attachment_entries(
    entries: list[dict[str, Any]],
    *,
    module_name: str,
    ingest: bool = True,
    action_name: str | None = None,
    app_instance: Any,
) -> list[dict[str, Any]] | None:
    uploaded: list[dict[str, Any]] = []
    for entry in list(entries or []):
        candidate = dict(entry or {})
        if str(candidate.get("storage_path") or candidate.get("path") or "").strip():
            uploaded.append(candidate)
            continue
        local_path = str(candidate.get("local_path") or "").strip()
        if not local_path:
            return None
        materialized = _upload_file_to_media_storage(
            local_path=local_path,
            module_name=module_name,
            ingest=bool(ingest),
            action_name=action_name,
            app_instance=app_instance,
        )
        if materialized is None:
            return None
        uploaded.append(materialized)
    return uploaded


class AttachmentRenderer(BaseRenderer):
    component_type = "Attachment"

    def render(
        self,
        props: dict,
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        container = QWidget()
        container.setObjectName(comp_id)
        container.setProperty("is_input", True)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        current_files = props.get("value", [])
        if not isinstance(current_files, list):
            current_files = []
        container.setProperty("value", list(current_files))
        container.setProperty("_confirmed_value", list(current_files))
        publish_bound_value(app_instance, container, comp_id, list(current_files))

        state: dict[str, Any] = {
            "surface_id": surface_id,
            "app_instance": app_instance,
            "comp_id": comp_id,
            "props": dict(props),
            "files": list(current_files),
            "container_widget": container,
        }
        container._attachment_state = state  # type: ignore[attr-defined]

        label_text = self._literal_text(props.get("label"))
        if label_text:
            label_widget = QLabel(label_text)
            label_widget.setProperty("ui_role", "form_label")
            layout.addWidget(label_widget)
            state["label_widget"] = label_widget

        # List of files
        files_container = QWidget()
        files_layout = QHBoxLayout(files_container)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(8)
        files_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        files_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(files_container)
        state["files_layout"] = files_layout
        state["files_container"] = files_container

        # Error label
        error_label = QLabel()
        error_label.setProperty("ui_role", "form_error_label")
        error_label.setWordWrap(True)
        error_label.hide()
        layout.addWidget(error_label)
        state["error_label"] = error_label

        # Upload button (custom tile for pixel parity with web renderer)
        upload_btn = UploadTile()
        upload_label = _upload_button_text(props.get("label"))
        upload_layout = QVBoxLayout(upload_btn)
        upload_layout.setContentsMargins(8, 8, 8, 8)
        upload_layout.setSpacing(6)
        upload_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_btn.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        upload_btn.setMinimumSize(QSize(_ATTACHMENT_TILE_SIZE, _ATTACHMENT_TILE_SIZE))
        upload_btn.setMaximumSize(QSize(_ATTACHMENT_TILE_SIZE, _ATTACHMENT_TILE_SIZE))

        upload_icon = QLabel()
        upload_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_icon.setPixmap(
            get_icon("ric.upload-2-line", color="#FAFAFA").pixmap(18, 18)
        )
        upload_icon.setFixedHeight(20)
        upload_layout.addStretch(1)
        upload_layout.addWidget(upload_icon, 0, Qt.AlignmentFlag.AlignHCenter)

        upload_text = QLabel(_wrap_text(upload_label))
        upload_text.setProperty("ui_role", "attachment_upload_btn_text")
        upload_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_text.setWordWrap(True)
        upload_text.setFixedHeight(30)
        upload_text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        upload_layout.addWidget(upload_text, 0, Qt.AlignmentFlag.AlignHCenter)
        upload_layout.addStretch(1)

        upload_btn.setToolTip(upload_label)
        upload_btn.setFixedSize(QSize(_ATTACHMENT_TILE_SIZE, _ATTACHMENT_TILE_SIZE))
        upload_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        upload_btn.setProperty("ui_role", "attachment_upload_btn")
        upload_btn.setProperty("error", "false")
        state["upload_label_widget"] = upload_text
        state["upload_btn"] = upload_btn

        def _on_upload():
            state_props = state.get("props", {})
            accept = state_props.get("accept", "")
            filter_str = self._convert_accept_to_filter(accept)

            if state_props.get("multiple"):
                paths, _ = QFileDialog.getOpenFileNames(
                    container, "Select Files", os.path.expanduser("~"), filter_str
                )
            else:
                path, _ = QFileDialog.getOpenFileName(
                    container, "Select File", os.path.expanduser("~"), filter_str
                )
                paths = [path] if path else []

            if paths:
                new_entries: list[dict[str, Any]] = []
                for local_path in paths:
                    local_entry = build_local_attachment_entry(str(local_path))
                    if local_entry is not None:
                        new_entries.append(local_entry)
                if not new_entries:
                    state_props["error"] = "File selection failed"
                    self._update_error_state(state)
                    return
                state_props["error"] = ""
                state["_previous_files"] = list(state.get("files", []))
                if state_props.get("multiple"):
                    state["files"].extend(new_entries)
                else:
                    state["files"] = [new_entries[0]]
                self._update_ui_and_emit(state)

        upload_btn.clicked.connect(_on_upload)

        # Initial render of files
        self._update_files_list(state)
        self._sync_button_visibility(state)

        return container

    def _convert_accept_to_filter(self, accept: str) -> str:
        if not accept:
            return "All Files (*)"

        parts = [p.strip() for p in accept.split(",")]
        filters = []
        for p in parts:
            if p == "image/*":
                filters.append("Images (*.png *.jpg *.jpeg *.gif *.webp)")
            elif p == "application/pdf":
                filters.append("PDF Files (*.pdf)")
            elif p.startswith("."):
                filters.append(f"Files (*{p})")
            else:
                filters.append(f"Other ({p})")

        return ";;".join(filters) + ";;All Files (*)"

    def _update_ui_and_emit(self, state: dict[str, Any]):
        app_instance = state.get("app_instance")
        container = state.get("container_widget")
        comp_id = state.get("comp_id")
        current_files = state.get("files", [])
        state_props = state.get("props", {})
        action = state_props.get("action") if isinstance(state_props, dict) else None
        confirm = action.get("confirm") if isinstance(action, dict) else None
        if action and not confirm_action(app_instance, confirm):
            previous_files = state.get("_previous_files")
            if not isinstance(previous_files, list) and container is not None:
                previous_files = container.property("_confirmed_value")
            state["files"] = list(previous_files if isinstance(previous_files, list) else [])
            self._update_files_list(state)
            self._sync_button_visibility(state)
            self._update_error_state(state)
            return

        # Update UI
        self._update_files_list(state)
        self._sync_button_visibility(state)
        self._update_error_state(state)

        # Emit action
        if container is not None:
            container.setProperty("value", list(current_files))
            container.setProperty("_confirmed_value", list(current_files))
        publish_bound_value(app_instance, container, comp_id, current_files)
        if "action" in state_props:
            act = state_props["action"]
            action_spec = act
            if isinstance(act, dict):
                action_spec = dict(act)
                action_spec.pop("confirm", None)
            emit_action_spec(
                app_instance,
                action_spec,
                {"value": current_files, comp_id: current_files},
                state.get("surface_id"),
                comp_id,
            )
        callback = getattr(container, "_form_on_value_changed", None)
        if callable(callback):
            callback()

    def _sync_button_visibility(self, state: dict[str, Any]):
        files_container = state.get("files_container")
        state_props = state.get("props", {})
        current_files = state.get("files", [])
        if files_container is None:
            return
        is_multiple = bool(state_props.get("multiple"))

        if not is_multiple:
            files_container.setFixedSize(
                QSize(_ATTACHMENT_TILE_SIZE, _ATTACHMENT_TILE_SIZE)
            )
        else:
            files_container.setMinimumSize(QSize(0, _ATTACHMENT_TILE_SIZE))
            files_container.setMaximumSize(QSize(16777215, _ATTACHMENT_TILE_SIZE))

    def _update_error_state(self, state: dict[str, Any]):
        error_label = state.get("error_label")
        label_widget = state.get("label_widget")
        state_props = state.get("props", {})
        if error_label is None:
            return
        error_text = state_props.get("error")
        if error_text:
            error_label.setText(self._literal_text(error_text))
            error_label.show()
            if label_widget is not None:
                label_widget.setProperty("error", True)
                label_widget.style().unpolish(label_widget)
                label_widget.style().polish(label_widget)
            upload_btn = state.get("upload_btn")
            if upload_btn is not None:
                upload_btn.setProperty("error", "true")
                upload_btn.style().unpolish(upload_btn)
                upload_btn.style().polish(upload_btn)
            upload_label_widget = state.get("upload_label_widget")
            if upload_label_widget is not None:
                upload_label_widget.setProperty("error", "true")
                upload_label_widget.style().unpolish(upload_label_widget)
                upload_label_widget.style().polish(upload_label_widget)
        else:
            error_label.hide()
            if label_widget is not None:
                label_widget.setProperty("error", False)
                label_widget.style().unpolish(label_widget)
                label_widget.style().polish(label_widget)
            upload_btn = state.get("upload_btn")
            if upload_btn is not None:
                upload_btn.setProperty("error", "false")
                upload_btn.style().unpolish(upload_btn)
                upload_btn.style().polish(upload_btn)
            upload_label_widget = state.get("upload_label_widget")
            if upload_label_widget is not None:
                upload_label_widget.setProperty("error", "false")
                upload_label_widget.style().unpolish(upload_label_widget)
                upload_label_widget.style().polish(upload_label_widget)

    def _update_files_list(self, state: dict[str, Any]):
        files = state.get("files", [])
        files_layout = state.get("files_layout")
        state_props = state.get("props", {})
        if files_layout is None:
            return
        is_multiple = bool(state_props.get("multiple"))
        upload_btn = state.get("upload_btn")
        # Clear previous
        while files_layout.count():
            item = files_layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            # Keep the shared upload tile alive; it is re-inserted below.
            if upload_btn is not None and widget is upload_btn:
                widget.hide()
                continue
            widget.deleteLater()

        if not files or not isinstance(files, list):
            render_files = []
        else:
            render_files = files if is_multiple else files[:1]

        for idx, f in enumerate(render_files):
            file_path = str(
                f.get("local_path")
                or f.get("path")
                or f.get("storage_path")
                or ""
            )
            has_existing_path = bool(file_path and os.path.exists(file_path))
            is_image = bool(has_existing_path and _is_image_path(file_path))
            is_pdf = bool(has_existing_path and _is_pdf_path(file_path))
            is_media = is_image or is_pdf

            row = QFrame()
            row.setFrameShape(QFrame.StyledPanel)
            row.setProperty("ui_role", "attachment_item")
            row.setProperty("attachment_kind", "image" if is_media else "generic")
            row.setFixedSize(QSize(_ATTACHMENT_TILE_SIZE, _ATTACHMENT_TILE_SIZE))
            row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            rem_btn = QToolButton()
            rem_btn.setIcon(get_icon("ric.close-line", color="#71717A"))
            rem_btn.setToolTip("Remove attachment")
            rem_btn.setProperty("ui_role", "attachment_remove_btn")
            rem_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rem_btn.setFixedSize(QSize(18, 18))

            def _make_remove_handler(i):
                return lambda: self._remove_file(state, i)

            rem_btn.clicked.connect(_make_remove_handler(idx))

            if is_media:
                gl = QGridLayout(row)
                gl.setContentsMargins(0, 0, 0, 0)
                gl.setSpacing(0)
                thumb_label = QLabel()
                thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb_label.setFixedSize(
                    QSize(_ATTACHMENT_TILE_SIZE, _ATTACHMENT_TILE_SIZE)
                )
                thumb_label.setScaledContents(False)
                pix = self._media_cover_preview(file_path)
                if not pix.isNull():
                    thumb_label.setPixmap(pix)
                gl.addWidget(thumb_label, 0, 0)
                gl.addWidget(
                    rem_btn,
                    0,
                    0,
                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                )
            else:
                rl = QVBoxLayout(row)
                rl.setContentsMargins(6, 6, 6, 6)
                rl.setSpacing(2)

                top = QHBoxLayout()
                top.setContentsMargins(0, 0, 0, 0)
                top.setSpacing(0)
                top.addStretch()
                top.addWidget(rem_btn)
                rl.addLayout(top)

                thumb_label = QLabel()
                thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb_label.setMinimumHeight(44)
                if file_path and os.path.exists(file_path):
                    thumb = self._get_thumbnail(file_path)
                    if thumb:
                        thumb_label.setPixmap(thumb)
                    else:
                        thumb_label.setPixmap(
                            get_icon("ric.file-line", color="#52525B").pixmap(24, 24)
                        )
                else:
                    thumb_label.setPixmap(
                        get_icon("ric.file-line", color="#52525B").pixmap(24, 24)
                    )
                rl.addWidget(thumb_label)

                name = str(f.get("name", "Unknown File"))
                name_lbl = QLabel(name)
                name_lbl.setProperty("ui_role", "attachment_item_label")
                name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                name_lbl.setWordWrap(False)
                name_lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.NoTextInteraction
                )
                name_lbl.setToolTip(name)
                metrics = name_lbl.fontMetrics()
                name_lbl.setText(
                    metrics.elidedText(name, Qt.TextElideMode.ElideRight, 82)
                )
                rl.addWidget(name_lbl)

            files_layout.addWidget(row)

        if upload_btn is not None:
            if is_multiple or len(render_files) == 0:
                upload_btn.show()
                files_layout.addWidget(upload_btn)
            else:
                upload_btn.hide()

        self._update_error_state(state)

    def _remove_file(self, state: dict[str, Any], index: int):
        current_files = state.get("files", [])
        if 0 <= index < len(current_files):
            state["_previous_files"] = list(current_files)
            current_files.pop(index)
            self._update_ui_and_emit(state)

    def _get_thumbnail(self, path: str) -> Optional[QPixmap]:
        ext = os.path.splitext(path)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            pix = QPixmap(path)
            if not pix.isNull():
                return pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        elif ext == ".pdf":
            return self._pdf_thumbnail(path, 32)
        return None

    def _media_cover_preview(self, path: str) -> QPixmap:
        base = QPixmap()
        if _is_pdf_path(path):
            pdf_preview = self._pdf_thumbnail(path, _ATTACHMENT_TILE_SIZE)
            if pdf_preview is not None and not pdf_preview.isNull():
                base = pdf_preview
        else:
            base = QPixmap(path)

        if base.isNull():
            return QPixmap()

        scaled = base.scaled(
            _ATTACHMENT_TILE_SIZE,
            _ATTACHMENT_TILE_SIZE,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - _ATTACHMENT_TILE_SIZE) // 2)
        y = max(0, (scaled.height() - _ATTACHMENT_TILE_SIZE) // 2)
        return scaled.copy(x, y, _ATTACHMENT_TILE_SIZE, _ATTACHMENT_TILE_SIZE)

    def _pdf_thumbnail(self, path: str, size: int = 32) -> Optional[QPixmap]:
        try:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(path)
            page = pdf[0]
            bitmap = page.render(scale=1, rotation=0, grayscale=False)
            pil_image = bitmap.to_pil()
            # Convert PIL to QPixmap
            import io

            buf = io.BytesIO()
            pil_image.save(buf, format="PNG")
            qpix = QPixmap()
            qpix.loadFromData(buf.getvalue())
            return qpix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception as e:
            print(f"Error generating PDF thumbnail: {e}")
            return None

    def update_widget_property(self, widget, prop, value):
        state = getattr(widget, "_attachment_state", None)
        if not isinstance(state, dict):
            return super().update_widget_property(widget, prop, value)

        state["container_widget"] = widget
        state_props = state.get("props", {})
        if not isinstance(state_props, dict):
            state_props = {}
            state["props"] = state_props

        if prop == "value":
            next_files = value if isinstance(value, list) else []
            state["files"] = next_files
            widget.setProperty("value", list(next_files))
            widget.setProperty("_confirmed_value", list(next_files))
            self._update_files_list(state)
            self._sync_button_visibility(state)
            return

        if prop == "error":
            state_props["error"] = value
            self._update_error_state(state)
            return

        if prop == "label":
            label_widget = state.get("label_widget")
            if label_widget is not None:
                label_widget.setText(self._literal_text(value))
            upload_label = _upload_button_text(value)
            upload_btn = state.get("upload_btn")
            if upload_btn is not None:
                upload_btn.setToolTip(upload_label)
            upload_label_widget = state.get("upload_label_widget")
            if upload_label_widget is not None:
                upload_label_widget.setText(_wrap_text(upload_label))
            return

        if prop == "action":
            state_props["action"] = value if isinstance(value, dict) else {}
            return

        if prop in {"multiple", "accept"}:
            state_props[prop] = value
            self._sync_button_visibility(state)
            return

        return super().update_widget_property(widget, prop, value)
