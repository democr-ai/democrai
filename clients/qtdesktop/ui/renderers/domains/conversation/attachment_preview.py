from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from ...base import BaseRenderer
from .message_list import (
    _load_attachment_bytes,
)


class AttachmentPreviewRenderer(BaseRenderer):
    component_type = "AttachmentPreview"

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        del surface_id
        root = QWidget()
        root.setObjectName(comp_id)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        mime_type = str(props.get("mime_type") or "").strip().lower()
        storage_path = str(props.get("storage_path") or "").strip()
        file_id = str(props.get("file_id") or "").strip()
        height = int(props.get("height") or 420)

        payload = _load_attachment_bytes(
            storage_path, file_id=file_id, app_instance=app_instance
        )
        if not payload:
            fallback = QLabel("Attachment preview not available.")
            fallback.setWordWrap(True)
            layout.addWidget(fallback)
            return root

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addStretch()
        download_btn = QPushButton("Download")
        toolbar_layout.addWidget(download_btn)
        layout.addWidget(toolbar)

        def _download() -> None:
            default_name = str(props.get("name") or "attachment.bin").strip() or "attachment.bin"
            filename, _ = QFileDialog.getSaveFileName(
                root,
                "Save attachment",
                default_name,
                "All Files (*)",
            )
            if not filename:
                return
            try:
                with open(filename, "wb") as handle:
                    handle.write(payload)
            except Exception:
                return

        download_btn.clicked.connect(_download)

        if mime_type.startswith("image/"):
            zoom_state = {"value": 1.0}
            pix = QPixmap()
            if pix.loadFromData(payload):
                minus_btn = QPushButton("-")
                plus_btn = QPushButton("+")
                zoom_label = QLabel("100%")
                toolbar_layout.insertWidget(0, minus_btn)
                toolbar_layout.insertWidget(1, zoom_label)
                toolbar_layout.insertWidget(2, plus_btn)
                image = QLabel()
                image.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                image.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
                scroller = QScrollArea()
                scroller.setWidgetResizable(True)
                scroller.setWidget(image)
                scroller.setMinimumHeight(max(260, height))

                def _render_zoom() -> None:
                    base_w = max(260, int(scroller.viewport().width() or 0) - 4)
                    scaled_w = int(max(220, base_w * float(zoom_state["value"])))
                    image.setPixmap(
                        pix.scaledToWidth(
                            scaled_w,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                    zoom_label.setText(f"{int(zoom_state['value'] * 100)}%")

                minus_btn.clicked.connect(
                    lambda *_: (
                        zoom_state.__setitem__(
                            "value", max(0.3, float(zoom_state["value"]) - 0.15)
                        ),
                        _render_zoom(),
                    )
                )
                plus_btn.clicked.connect(
                    lambda *_: (
                        zoom_state.__setitem__(
                            "value", min(4.0, float(zoom_state["value"]) + 0.15)
                        ),
                        _render_zoom(),
                    )
                )
                scroller.resizeEvent = lambda event: (
                    QScrollArea.resizeEvent(scroller, event),
                    _render_zoom(),
                )
                _render_zoom()
                layout.addWidget(scroller)
                return root

        if mime_type == "application/pdf":
            from .pdf_viewer import PdfViewerRenderer

            pdf_widget = PdfViewerRenderer().render(
                {
                    "name": props.get("name") or "document.pdf",
                    "storage_path": storage_path,
                    "file_id": file_id,
                    "url": props.get("url") or "",
                    "height": height,
                    "fit": "container",
                },
                "drawer",
                app_instance,
                f"{comp_id}_pdf_viewer",
            )
            layout.addWidget(pdf_widget, 1)
            return root

        fallback = QLabel("Preview not supported for this attachment type.")
        fallback.setWordWrap(True)
        layout.addWidget(fallback)
        return root
