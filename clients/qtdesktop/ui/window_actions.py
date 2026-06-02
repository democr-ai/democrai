from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMainWindow


def center_window(window: QMainWindow) -> None:
    """Center a QMainWindow on the primary screen."""
    screen = QGuiApplication.primaryScreen().geometry()
    size = window.geometry()
    x = (screen.width() - size.width()) // 2
    y = (screen.height() - size.height()) // 2
    window.move(x, y)


def _resolve_window_url(window: QMainWindow, raw_url: str) -> str:
    url = str(raw_url or "").strip()
    if not url:
        return ""
    if url.startswith("/"):
        host = str(getattr(window, "host", "127.0.0.1") or "127.0.0.1")
        port = int(getattr(window, "port", 8000) or 8000)
        return f"http://{host}:{port}{url}"
    return url


def _download_window_url(
    window: QMainWindow, *, url: str, suggested_filename: str = ""
) -> None:
    request_url = _resolve_window_url(window, url)
    if not request_url:
        return
    jwt = str(getattr(window, "jwt", "") or "").strip()
    headers = {"Accept": "*/*"}
    if jwt:
        headers["X-JWT"] = jwt
    request = urllib.request.Request(url=request_url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30.0) as response:  # nosec B310
            payload = bytes(response.read() or b"")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return
    if not payload:
        return
    parsed = urllib.parse.urlparse(request_url)
    fallback_name = os.path.basename(parsed.path or "") or "download"
    default_name = str(suggested_filename or "").strip() or fallback_name
    target_path, _ = QFileDialog.getSaveFileName(
        window,
        "Salva file",
        default_name,
    )
    if not target_path:
        return
    try:
        with open(target_path, "wb") as handle:
            handle.write(payload)
    except OSError:
        return


def apply_window_action(window: QMainWindow, action: dict) -> None:
    """Apply server-driven window action (`resize`, `maximize`, `center`)."""
    op = action.get("op")
    trace = getattr(window, "_startup_trace", None)
    if callable(trace):
        trace(
            "window_action",
            op=op,
            width=action.get("width"),
            height=action.get("height"),
            current_size=f"{window.width()}x{window.height()}",
        )
    if op == "resize":
        window.showNormal()  # Must be normal to resize
        width = action.get("width", 1100)
        height = action.get("height", 800)
        window.resize(width, height)
        if callable(trace):
            trace("window_resized", size=f"{window.width()}x{window.height()}")
    elif op == "maximize":
        window.showMaximized()
        if callable(trace):
            trace("window_maximized", size=f"{window.width()}x{window.height()}")
    elif op == "center":
        center_window(window)
        if callable(trace):
            trace("window_centered", size=f"{window.width()}x{window.height()}")
    elif op == "copy_to_clipboard":
        text = str(action.get("text", ""))
        if text:
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
    elif op == "open_url":
        url = _resolve_window_url(window, str(action.get("url", "") or ""))
        if not url:
            return
        if bool(action.get("download", False)):
            _download_window_url(
                window,
                url=url,
                suggested_filename=str(action.get("filename", "") or ""),
            )
            return
        QDesktopServices.openUrl(QUrl(url))
