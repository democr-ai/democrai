from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Optional

import shiboken6
from PySide6.QtCore import QRegularExpression, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QSyntaxHighlighter
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QTextBrowser,
)


class NoScrollCodeBlock(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameStyle(0)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().contentsChanged.connect(self._schedule_recalc)

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
        self._schedule_recalc()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._schedule_recalc()

    def _schedule_recalc(self):
        QTimer.singleShot(0, self._recalc_height)

    def _recalc_height(self):
        if not shiboken6.isValid(self):
            return
        doc = self.document()
        blocks = doc.blockCount()
        fm = self.fontMetrics()
        h = blocks * fm.lineSpacing()
        m = self.contentsMargins()
        h += m.top() + m.bottom() + 16
        self.setFixedHeight(max(1, h))


@dataclass
class Segment:
    kind: str
    text: str
    lang: Optional[str] = None


FENCED_RE = re.compile(r"```(?P<lang>[A-Za-z0-9_+-]*)\n(?P<code>.*?)(?:\n)?```", re.DOTALL)


def split_markdown(md: str) -> List[Segment]:
    segments: List[Segment] = []
    pos = 0
    for m in FENCED_RE.finditer(md):
        start, end = m.span()
        if start > pos:
            segments.append(Segment("md", md[pos:start]))
        lang = (m.group("lang") or "").strip().lower() or None
        code = m.group("code")
        segments.append(Segment("code", code, lang=lang))
        pos = end
    if pos < len(md):
        segments.append(Segment("md", md[pos:]))
    return [s for s in segments if s.text.strip() != ""]


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self.rules = []

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#569CD6"))
        kw_fmt.setFontWeight(QFont.Bold)
        for w in [
            "def", "class", "return", "if", "elif", "else", "for", "while", "import",
            "from", "try", "except", "with", "as", "pass", "break", "continue", "True",
            "False", "None",
        ]:
            self.rules.append((QRegularExpression(rf"\b{w}\b"), kw_fmt))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#CE9178"))
        self.rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
        self.rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), str_fmt))

        cmt_fmt = QTextCharFormat()
        cmt_fmt.setForeground(QColor("#6A9955"))
        cmt_fmt.setFontItalic(True)
        self.rules.append((QRegularExpression(r"#.*"), cmt_fmt))

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#B5CEA8"))
        self.rules.append((QRegularExpression(r"\b\d+(\.\d+)?\b"), num_fmt))

    def highlightBlock(self, text: str):
        for pattern, fmt in self.rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


def make_code_widget(code: str, lang: Optional[str]) -> QPlainTextEdit:
    w = NoScrollCodeBlock()
    w.setPlainText(code)
    w.setReadOnly(True)
    w.setFrameStyle(0)
    w.setLineWrapMode(QPlainTextEdit.NoWrap)
    w.setFont(QFont("Consolas", 10))
    if lang in ("py", "python"):
        w._highlighter = PythonHighlighter(w.document())
    return w


def make_md_widget(md_text: str) -> QTextBrowser:
    w = QTextBrowser()
    w.setOpenExternalLinks(True)
    w.setFrameStyle(0)
    w.setProperty("ui_role", "markdown_browser")
    w.setMarkdown(md_text)
    w.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    w.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def update_height():
        if not shiboken6.isValid(w):
            return
        doc = w.document()
        doc.setTextWidth(w.viewport().width())
        height = int(doc.size().height() + 16)
        w.setFixedHeight(height)

    QTimer.singleShot(0, update_height)
    return w


def escape_qt_mnemonic(text: Any) -> str:
    raw = "" if text is None else str(text)
    return raw.replace("&", "&&")
