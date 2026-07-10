"""TikZ code editor: syntax highlighting, autocompletion, number scrubbing."""

import re

from PyQt6.QtCore import Qt, QRegularExpression, QStringListModel
from PyQt6.QtGui import (QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
                         QTextCursor)
from PyQt6.QtWidgets import QPlainTextEdit, QCompleter

TIKZ_KEYWORDS = [
    "\\draw", "\\node", "\\fill", "\\filldraw", "\\path", "\\coordinate",
    "\\shade", "\\clip", "\\begin{tikzpicture}", "\\end{tikzpicture}",
    "\\begin{scope}", "\\end{scope}", "\\foreach", "\\includegraphics",
    "rectangle", "circle", "ellipse", "arc", "grid", "cycle", "controls",
    "coordinates", "plot[smooth]", "node", "child", "line width=", "color=",
    "fill=", "draw=", "opacity=", "dashed", "dotted", "thick", "very thick",
    "ultra thick", "thin", "step=", "rounded corners", "->", "<->", "<-",
    "-Stealth", "anchor=", "above", "below", "left", "right", "midway",
    "pos=", "scale=", "rotate=", "shift=", "xshift=", "yshift=",
    "red", "blue", "green", "orange", "purple", "gray", "black", "white",
    "yellow", "cyan", "magenta", "brown", "teal", "violet", "pink",
    "star", "regular polygon", "ellipse callout", "cloud callout",
    "minimum width=", "minimum height=", "text width=", "align=center",
]


class TikzHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            f.setFontItalic(italic)
            return f
        self.rules = [
            (QRegularExpression(r"\\[a-zA-Z@]+"), fmt("#1d4ed8", bold=True)),
            (QRegularExpression(r"[-+]?\d*\.?\d+"), fmt("#b45309")),
            (QRegularExpression(r"\[[^\[\]]*\]"), fmt("#047857")),
            (QRegularExpression(r"[{}();]"), fmt("#6b7280")),
            (QRegularExpression(r"--|\.\."), fmt("#be185d", bold=True)),
        ]
        self.comment = fmt("#9ca3af", italic=True)

    def highlightBlock(self, text):
        for rx, f in self.rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), f)
        # comments override everything after an unescaped %
        i = 0
        while i < len(text):
            if text[i] == "%" and (i == 0 or text[i - 1] != "\\"):
                self.setFormat(i, len(text) - i, self.comment)
                break
            i += 1


NUM_RE = re.compile(r"[-+]?\d*\.?\d+")


class TikzEditor(QPlainTextEdit):
    """Plain-text TikZ editor.

    * Ctrl+Space  -> completion popup (also triggers automatically after '\\')
    * Ctrl+Wheel over a number -> scrub it up/down (0.25 steps,
      +Shift = 1.0 steps)
    """

    def __init__(self):
        super().__init__()
        font = QFont("Monospace", 10)
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.highlighter = TikzHighlighter(self.document())

        self.completer = QCompleter(self)
        self.completer.setModel(QStringListModel(TIKZ_KEYWORDS))
        self.completer.setWidget(self)
        self.completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self._insert_completion)

    # -- completion --------------------------------------------------------
    def _word_under_cursor(self) -> str:
        tc = self.textCursor()
        text = tc.block().text()[: tc.positionInBlock()]
        m = re.search(r"(\\?[A-Za-z]*)$", text)
        return m.group(1) if m else ""

    def _insert_completion(self, completion: str):
        tc = self.textCursor()
        prefix = self._word_under_cursor()
        for _ in range(len(prefix)):
            tc.deletePreviousChar()
        tc.insertText(completion)
        self.setTextCursor(tc)

    def keyPressEvent(self, ev):
        if self.completer.popup().isVisible() and ev.key() in (
                Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab,
                Qt.Key.Key_Escape):
            ev.ignore()
            return
        if (ev.key() == Qt.Key.Key_Space
                and ev.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._popup_completions()
            return
        super().keyPressEvent(ev)
        prefix = self._word_under_cursor()
        if prefix.startswith("\\") and len(prefix) >= 2:
            self._popup_completions()
        elif self.completer.popup().isVisible():
            if len(prefix) < 1:
                self.completer.popup().hide()
            else:
                self.completer.setCompletionPrefix(prefix)

    def _popup_completions(self):
        prefix = self._word_under_cursor()
        self.completer.setCompletionPrefix(prefix)
        if self.completer.completionCount() == 0:
            self.completer.popup().hide()
            return
        rect = self.cursorRect()
        rect.setWidth(self.completer.popup().sizeHintForColumn(0) + 24)
        self.completer.complete(rect)

    # -- number scrubbing ---------------------------------------------------
    def wheelEvent(self, ev):
        if not ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return super().wheelEvent(ev)
        pos_cursor = self.cursorForPosition(ev.position().toPoint())
        block = pos_cursor.block()
        col = pos_cursor.positionInBlock()
        text = block.text()
        for m in NUM_RE.finditer(text):
            if m.start() <= col <= m.end():
                step = 1.0 if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.25
                delta = step if ev.angleDelta().y() > 0 else -step
                try:
                    val = float(m.group(0)) + delta
                except ValueError:
                    return
                new = f"{val:.3f}".rstrip("0").rstrip(".") or "0"
                tc = QTextCursor(block)
                tc.setPosition(block.position() + m.start())
                tc.setPosition(block.position() + m.end(),
                               QTextCursor.MoveMode.KeepAnchor)
                tc.insertText(new)
                ev.accept()
                return
        super().wheelEvent(ev)
