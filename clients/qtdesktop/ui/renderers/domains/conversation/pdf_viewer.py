from __future__ import annotations

import os
import tempfile
from typing import Any, Dict

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ....i18n import get_i18n
from ...base import BaseRenderer
from ...icon import get_icon
from ..media.common import resolve_runtime_media_source
from .message_list import _load_attachment_bytes, _pdf_first_page_pixmap


class PdfViewerRenderer(BaseRenderer):
    component_type = "PdfViewer"

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
            "name": self.COMPONENT,
            "storage_path": self.COMPONENT,
            "file_id": self.COMPONENT,
            "url": self.COMPONENT,
            "height": self.COMPONENT,
            "fit": self.COMPONENT,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        messages = get_i18n(app_instance)
        name = (
            str(
                self._resolve_initial_value(
                    props.get("name"),
                    surface_id=surface_id,
                    app_instance=app_instance,
                    default="document.pdf",
                )
                or "document.pdf"
            ).strip()
            or "document.pdf"
        )
        storage_path = str(
            self._resolve_initial_value(
                props.get("storage_path"),
                surface_id=surface_id,
                app_instance=app_instance,
                default="",
            )
            or ""
        ).strip()
        url = str(
            self._resolve_initial_value(
                props.get("url"),
                surface_id=surface_id,
                app_instance=app_instance,
                default="",
            )
            or ""
        ).strip()
        path = resolve_runtime_media_source(
            storage_path or url,
            app_instance,
        )
        file_id = str(
            self._resolve_initial_value(
                props.get("file_id"),
                surface_id=surface_id,
                app_instance=app_instance,
                default="",
            )
            or ""
        ).strip()
        height = int(
            self._resolve_initial_value(
                props.get("height"),
                surface_id=surface_id,
                app_instance=app_instance,
                default=520,
            )
            or 520
        )
        fit = (
            str(
                self._resolve_initial_value(
                    props.get("fit"),
                    surface_id=surface_id,
                    app_instance=app_instance,
                    default="",
                )
                or ""
            )
            .strip()
            .lower()
        )
        payload = _load_attachment_bytes(
            path, file_id=file_id, app_instance=app_instance
        )

        root = QWidget()
        root.setObjectName(comp_id)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if not payload:
            label = QLabel(messages["pdf_not_available"])
            label.setWordWrap(True)
            layout.addWidget(label)
            return root

        def _download() -> None:
            filename, _ = QFileDialog.getSaveFileName(
                root,
                messages["pdf_save_title"],
                name,
                "PDF Files (*.pdf);;All Files (*)",
            )
            if not filename:
                return
            try:
                with open(filename, "wb") as handle:
                    handle.write(payload)
            except Exception:
                return

        viewer, temp_path = self._build_qtpdf_widget(
            payload=payload,
            height=height,
            name=name,
            fit=fit,
            messages=messages,
        )
        if viewer is not None:
            layout.addWidget(viewer, 1)
            if temp_path:
                root.destroyed.connect(
                    lambda *_: os.path.exists(temp_path) and os.unlink(temp_path)
            )
            return root

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addStretch()
        download_btn = QPushButton(messages["pdf_download"])
        download_btn.clicked.connect(_download)
        toolbar_layout.addWidget(download_btn)
        layout.addWidget(toolbar)

        viewer = self._build_pdfium_widget(
            payload=payload,
            height=height,
            name=name,
            fit=fit,
            messages=messages,
        )
        if viewer is not None:
            layout.addWidget(viewer, 1)
            return root

        # Last-resort fallback when pypdfium2 is unavailable.
        pix = _pdf_first_page_pixmap(payload, 760)
        if pix is not None:
            fallback = QLabel()
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setPixmap(pix)
            fallback.setStyleSheet(
                "background: #f4f4f5; padding: 12px; border: 1px solid #e4e4e7; border-radius: 8px;"
            )
            layout.addWidget(fallback, 1)
            return root

        label = QLabel(messages["pdf_preview_unavailable"])
        label.setWordWrap(True)
        layout.addWidget(label)
        return root

    def _build_qtpdf_widget(
        self,
        *,
        payload: bytes,
        height: int,
        name: str,
        fit: str = "",
        messages: dict[str, str],
    ) -> tuple[QWidget | None, str]:
        try:
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPdfWidgets import QPdfView
        except Exception:
            return None, ""

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".pdf",
                prefix="democrai-pdfviewer-",
                delete=False,
            ) as handle:
                handle.write(payload)
                pdf_path = str(handle.name)
        except Exception:
            return None, ""

        document = QPdfDocument()
        try:
            document.load(pdf_path)
        except Exception:
            return None, pdf_path
        try:
            error_none = getattr(QPdfDocument.Error, "None_", None)
            if error_none is not None and document.error() != error_none:
                return None, pdf_path
        except Exception:
            pass

        total_pages = max(0, int(document.pageCount() or 0))
        if total_pages < 1:
            return None, pdf_path

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(8)

        def _dark_icon_button(
            icon_name: str,
            tooltip: str,
            *,
            checkable: bool = False,
            size: int = 34,
        ) -> QToolButton:
            button = QToolButton()
            button.setCheckable(checkable)
            button.setIcon(get_icon(icon_name, "#e5e7eb", 18))
            button.setIconSize(QSize(18, 18))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setToolTip(tooltip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(size, size)
            button.setStyleSheet(
                "QToolButton {"
                "  background: #1f2937;"
                "  border: 1px solid #374151;"
                "  border-radius: 8px;"
                "  color: #e5e7eb;"
                "}"
                "QToolButton:hover { background: #374151; border-color: #4b5563; }"
                "QToolButton:pressed, QToolButton:checked { background: #0f766e; border-color: #14b8a6; }"
                "QToolButton:disabled { background: #111827; border-color: #1f2937; color: #6b7280; }"
            )
            return button

        toolbar = QWidget()
        toolbar.setStyleSheet(
            "background: #111827; border: 1px solid #1f2937; border-radius: 10px;"
        )
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(8)

        sidebar_btn = _dark_icon_button(
            "ric.sidebar-fold-line",
            messages["pdf_show_thumbnails"],
            checkable=True,
        )
        prev_btn = _dark_icon_button("ric.arrow-left-s-line", messages["pdf_previous_page"])
        next_btn = _dark_icon_button("ric.arrow-right-s-line", messages["pdf_next_page"])
        page_input = QLineEdit()
        page_input.setFixedWidth(56)
        page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_input.setStyleSheet(
            "QLineEdit {"
            "  background: #0b1220;"
            "  border: 1px solid #374151;"
            "  border-radius: 7px;"
            "  color: #f9fafb;"
            "  padding: 4px 6px;"
            "}"
        )
        page_count_label = QLabel(f"/ {total_pages}")
        page_count_label.setStyleSheet("color: #9ca3af;")
        minus_btn = _dark_icon_button("ric.zoom-out-line", messages["pdf_zoom_out"])
        plus_btn = _dark_icon_button("ric.zoom-in-line", messages["pdf_zoom_in"])
        fit_btn = _dark_icon_button("ric.fullscreen-line", messages["pdf_fit_width"])
        zoom_label = QLabel(messages["pdf_fit_width"])
        zoom_label.setMinimumWidth(90)
        zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_label.setStyleSheet("color: #d1d5db;")
        title_label = QLabel(name)
        title_label.setWordWrap(False)
        title_label.setStyleSheet("color: #f9fafb; font-weight: 600;")
        download_btn = _dark_icon_button("ric.download-line", messages["pdf_download"])

        toolbar_layout.addWidget(sidebar_btn)
        toolbar_layout.addWidget(title_label, 1)
        toolbar_layout.addWidget(prev_btn)
        toolbar_layout.addWidget(page_input)
        toolbar_layout.addWidget(page_count_label)
        toolbar_layout.addWidget(next_btn)
        toolbar_layout.addSpacing(4)
        toolbar_layout.addWidget(minus_btn)
        toolbar_layout.addWidget(plus_btn)
        toolbar_layout.addWidget(fit_btn)
        toolbar_layout.addWidget(zoom_label)
        toolbar_layout.addWidget(download_btn)
        root_layout.addWidget(toolbar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)

        thumbnails = QListWidget()
        thumbnails.setIconSize(QSize(120, 170))
        thumbnails.setSpacing(8)
        thumbnails.setUniformItemSizes(False)
        thumbnails.setFixedWidth(164)
        thumbnails.setStyleSheet(
            "QListWidget {"
            "  background: #111827;"
            "  border: 1px solid #1f2937;"
            "  border-radius: 10px;"
            "  padding: 8px;"
            "}"
            "QListWidget::item { color: #d1d5db; padding: 6px; border-radius: 7px; }"
            "QListWidget::item:hover { background: #1f2937; }"
            "QListWidget::item:selected { background: #0f766e; color: #f9fafb; }"
        )
        thumbnails.hide()

        view = QPdfView()
        view.setDocument(document)
        view.setMinimumHeight(max(300, int(height or 520)))
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        try:
            view.setPageMode(QPdfView.PageMode.MultiPage)
        except Exception:
            pass
        try:
            view.setZoomMode(QPdfView.ZoomMode.FitToWidth if fit == "container" else QPdfView.ZoomMode.Custom)
            if fit != "container":
                view.setZoomFactor(1.0)
                zoom_label.setText("100%")
        except Exception:
            pass

        body_layout.addWidget(thumbnails)
        body_layout.addWidget(view, 1)
        root_layout.addWidget(body, 1)

        navigator = view.pageNavigator()
        state = {"zoom": 1.0}

        def _build_thumbnails() -> None:
            thumbnails.clear()
            for page in range(total_pages):
                page_size = document.pagePointSize(page)
                if page_size.width() <= 0 or page_size.height() <= 0:
                    image_size = QSize(120, 170)
                else:
                    image_size = QSize(
                        120,
                        max(1, round(120 * page_size.height() / page_size.width())),
                    )
                image = document.render(page, image_size)
                item = QListWidgetItem(f"{messages['pdf_page']} {page + 1}")
                if not image.isNull():
                    item.setIcon(QIcon(QPixmap.fromImage(image)))
                item.setData(Qt.ItemDataRole.UserRole, page)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                thumbnails.addItem(item)

        def _current_page() -> int:
            try:
                return int(navigator.currentPage())
            except Exception:
                return 0

        def _sync_page_controls(*_args) -> None:
            current_page = max(0, min(total_pages - 1, _current_page()))
            page_input.setText(str(current_page + 1))
            prev_btn.setEnabled(current_page > 0)
            next_btn.setEnabled(current_page < total_pages - 1)
            thumbnails.blockSignals(True)
            thumbnails.setCurrentRow(current_page)
            thumbnails.blockSignals(False)

        def _go_to_page(page: int) -> None:
            idx = max(0, min(total_pages - 1, int(page)))
            try:
                navigator.jump(idx, QPointF(0, 0))
            except Exception:
                return
            _sync_page_controls()

        def _go_to_page_from_input() -> None:
            try:
                page = int(page_input.text()) - 1
            except ValueError:
                _sync_page_controls()
                return
            _go_to_page(page)

        def _go_to_thumbnail_page(item: QListWidgetItem) -> None:
            page = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(page, int):
                _go_to_page(page)

        def _apply_zoom(value: float) -> None:
            state["zoom"] = max(0.1, min(8.0, float(value)))
            try:
                view.setZoomMode(QPdfView.ZoomMode.Custom)
                view.setZoomFactor(float(state["zoom"]))
            except Exception:
                return
            zoom_label.setText(f"{int(float(state['zoom']) * 100)}%")

        def _fit_width() -> None:
            try:
                view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
                zoom_label.setText(messages["pdf_fit_width"])
            except Exception:
                _apply_zoom(1.0)

        def _download_qtpdf() -> None:
            filename, _ = QFileDialog.getSaveFileName(
                root,
                messages["pdf_save_title"],
                name,
                "PDF Files (*.pdf);;All Files (*)",
            )
            if not filename:
                return
            try:
                with open(filename, "wb") as handle:
                    handle.write(payload)
            except Exception:
                return

        sidebar_btn.toggled.connect(thumbnails.setVisible)
        prev_btn.clicked.connect(lambda *_: _go_to_page(_current_page() - 1))
        next_btn.clicked.connect(lambda *_: _go_to_page(_current_page() + 1))
        page_input.returnPressed.connect(_go_to_page_from_input)
        thumbnails.itemClicked.connect(_go_to_thumbnail_page)
        minus_btn.clicked.connect(lambda *_: _apply_zoom(float(state["zoom"]) * 0.85))
        plus_btn.clicked.connect(lambda *_: _apply_zoom(float(state["zoom"]) * 1.15))
        fit_btn.clicked.connect(_fit_width)
        download_btn.clicked.connect(_download_qtpdf)
        try:
            navigator.currentPageChanged.connect(_sync_page_controls)
        except Exception:
            pass

        _build_thumbnails()
        if fit == "container":
            _fit_width()
        _go_to_page(0)
        _sync_page_controls()

        root._pdf_document = document  # type: ignore[attr-defined]
        root._pdf_view = view  # type: ignore[attr-defined]
        root._pdf_temp_path = pdf_path  # type: ignore[attr-defined]
        return root, pdf_path

    def _build_pdfium_widget(
        self,
        *,
        payload: bytes,
        height: int,
        name: str,
        fit: str = "",
        messages: dict[str, str],
    ) -> QWidget | None:
        try:
            import pypdfium2 as pdfium
        except Exception:
            return None
        try:
            document = pdfium.PdfDocument(payload)
            total_pages = int(len(document))
            if total_pages < 1:
                return None
        except Exception:
            return None

        def _page_size(index: int) -> tuple[float, float]:
            try:
                page = document[int(index)]
                width, page_height = page.get_size()
                return float(width), float(page_height)
            except Exception:
                return 595.0, 842.0

        def _render_pixmap(index: int, zoom: float) -> QPixmap | None:
            try:
                page = document[int(index)]
                pil_img = page.render(scale=(float(zoom))).to_pil()
                data = pil_img.tobytes("raw", "RGBA")
                qimage = QImage(
                    data,
                    pil_img.width,
                    pil_img.height,
                    QImage.Format.Format_RGBA8888,
                ).copy()
                return QPixmap.fromImage(qimage)
            except Exception:
                return None

        fit_container = fit == "container"

        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(8)

        toolbar = QWidget()
        toolbar.setStyleSheet(
            "background: #ffffff; border: 1px solid #e4e4e7; border-radius: 10px;"
        )
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(8)

        prev_btn = QPushButton("<")
        next_btn = QPushButton(">")
        minus_btn = QPushButton("-")
        plus_btn = QPushButton("+")
        fit_btn = QPushButton(messages["pdf_fit_width"])
        page_label = QLabel("1 / 1")
        zoom_label = QLabel(messages["pdf_fit_width"])
        page_label.setStyleSheet("color: #52525b; font-weight: 600;")
        zoom_label.setStyleSheet("color: #71717a;")

        for w in (prev_btn, next_btn, minus_btn, plus_btn, fit_btn):
            w.setCursor(Qt.CursorShape.PointingHandCursor)
            w.setMinimumWidth(34)
            w.setStyleSheet(
                "QPushButton {"
                "  background: #f8fafc;"
                "  border: 1px solid #d4d4d8;"
                "  border-radius: 8px;"
                "  color: #111827;"
                "  font-weight: 600;"
                "  padding: 4px 8px;"
                "}"
                "QPushButton:hover { background: #f1f5f9; }"
                "QPushButton:pressed { background: #e2e8f0; }"
                "QPushButton:disabled { color: #9ca3af; border-color: #e5e7eb; background: #f9fafb; }"
            )
        fit_btn.setMinimumWidth(44)
        if fit_container:
            minus_btn.setEnabled(False)
            plus_btn.setEnabled(False)

        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(page_label)
        toolbar_layout.addSpacing(8)
        toolbar_layout.addWidget(prev_btn)
        toolbar_layout.addWidget(next_btn)
        toolbar_layout.addSpacing(4)
        toolbar_layout.addWidget(minus_btn)
        toolbar_layout.addWidget(plus_btn)
        toolbar_layout.addWidget(fit_btn)
        toolbar_layout.addWidget(zoom_label)
        shell_layout.addWidget(toolbar)

        frame = QWidget()
        frame.setStyleSheet(
            "background: #f4f4f5; border: 1px solid #e4e4e7; border-radius: 10px;"
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(0)

        scroller = QScrollArea()
        scroller.setWidgetResizable(False)
        scroller.setMinimumHeight(max(300, int(height or 520)))
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            if fit_container
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroller.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroller.setStyleSheet("background: transparent; border: none;")
        scroller.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        page_wrap = QWidget()
        page_wrap.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        page_wrap_layout = QVBoxLayout(page_wrap)
        page_wrap_layout.setContentsMargins(6, 6, 6, 6)
        page_wrap_layout.setSpacing(0)
        page_wrap_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )

        page_image = QLabel()
        page_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_image.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        page_image.setStyleSheet(
            "background: #ffffff;"
            "border: 1px solid #a1a1aa;"
            "border-bottom: 2px solid #71717a;"
        )
        page_wrap_layout.addWidget(page_image, 0, Qt.AlignmentFlag.AlignCenter)
        scroller.setWidget(page_wrap)

        state = {
            "page": 0,
            "pages": total_pages,
            "zoom": 1.0,
            "fit_mode": True,
        }

        def _sync_labels() -> None:
            page_label.setText(f"{int(state['page']) + 1} / {int(state['pages'])}")
            prev_btn.setEnabled(int(state["page"]) > 0)
            next_btn.setEnabled(int(state["page"]) < (int(state["pages"]) - 1))
            zoom_label.setText(
                messages["pdf_fit_width"]
                if bool(state["fit_mode"])
                else f"{int(float(state['zoom']) * 100)}%"
            )

        def _fit_zoom_for_current_page() -> float:
            # Keep a safety gutter to avoid clipping from borders/scrollbar rounding.
            # Use a stronger vertical gutter because the drawer/theme introduces
            # additional runtime paddings not reflected in raw viewport size.
            viewport_w = max(200, int(scroller.viewport().width() or 0) - 40)
            viewport_h = max(200, int(scroller.viewport().height() or 0) - 56)
            page_w, page_h = _page_size(int(state["page"]))
            ratio_w = float(viewport_w) / max(1.0, float(page_w))
            ratio_h = float(viewport_h) / max(1.0, float(page_h))
            ratio = min(ratio_w, ratio_h) * 0.92
            return max(0.3, min(4.0, ratio))

        def _render_current_page() -> None:
            if fit_container:
                state["fit_mode"] = True
            if bool(state["fit_mode"]):
                state["zoom"] = _fit_zoom_for_current_page()
            pix = _render_pixmap(int(state["page"]), float(state["zoom"]))
            if pix is None:
                page_image.clear()
                _sync_labels()
                return
            display_scale = 0.95 if bool(state["fit_mode"]) else 1.0
            if display_scale < 1.0:
                shown_pix = pix.scaled(
                    int(max(1, pix.width() * display_scale)),
                    int(max(1, pix.height() * display_scale)),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            else:
                shown_pix = pix
            page_image.setPixmap(shown_pix)
            page_image.setFixedSize(shown_pix.size())
            page_wrap.setFixedSize(page_image.width() + 12, page_image.height() + 12)
            scroller.verticalScrollBar().setValue(0)
            _sync_labels()

        def _apply_fit() -> None:
            state["fit_mode"] = True
            _render_current_page()

        def _apply_zoom(value: float) -> None:
            if fit_container:
                return
            state["fit_mode"] = False
            state["zoom"] = max(0.3, min(4.0, float(value)))
            _render_current_page()

        def _go_page(target: int) -> None:
            idx = max(0, min(int(state["pages"]) - 1, int(target)))
            state["page"] = idx
            _render_current_page()
            scroller.verticalScrollBar().setValue(0)

        prev_btn.clicked.connect(lambda *_: _go_page(int(state["page"]) - 1))
        next_btn.clicked.connect(lambda *_: _go_page(int(state["page"]) + 1))
        minus_btn.clicked.connect(lambda *_: _apply_zoom(float(state["zoom"]) - 0.15))
        plus_btn.clicked.connect(lambda *_: _apply_zoom(float(state["zoom"]) + 0.15))
        fit_btn.clicked.connect(lambda *_: _apply_fit())

        # Keep "fit" responsive when container width changes.
        scroller.resizeEvent = lambda event: (
            QScrollArea.resizeEvent(scroller, event),
            _render_current_page() if bool(state["fit_mode"]) else None,
        )
        frame_layout.addWidget(scroller, 1)
        shell_layout.addWidget(frame, 1)

        _apply_fit()
        _go_page(0)
        shell._pdf_document = document  # type: ignore[attr-defined]
        return shell
