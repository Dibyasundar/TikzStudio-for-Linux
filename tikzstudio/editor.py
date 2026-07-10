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
    "minimum width=", "minimum height=", "minimum size=", "text width=",
    "align=center", "align=left", "align=right", "anchor=west",
    "anchor=east", "anchor=north", "anchor=south", "anchor=center",
    "anchor=north east", "anchor=north west", "anchor=south east",
    "anchor=south west", "rounded corners", "rounded corners=8pt",
    "fill opacity=", "draw opacity=", "line cap=round", "line join=round",
    "dash pattern=on 4pt off 2pt", "double", "double distance=",
    "decorate", "decoration=snake", "decoration=zigzag",
    "decoration={coil, aspect=0.6}", "decoration={brace, amplitude=6pt}",
    "\\includegraphics[width=3cm]{}", "width=", "height=",
    "keepaspectratio", "angle=", "\\begin{scope}", "\\end{scope}",
    "shift={(0,0)}", "inner sep=", "outer sep=", "circle callout",
    "cloud callout", "single arrow", "double arrow", "starburst",
    "regular polygon sides=", "star points=", "aspect=",
    "\\usetikzlibrary{}", "\\usepackage{}", "smooth", "tension=",
    "domain=", "samples=", "variable=", "loop above", "loop below",
    "bend left", "bend right", "out=", "in=", "pos=0.5", "sloped",
    "\\pgfsetlinewidth{1pt}", "\\pgfsetdash{{3pt}{2pt}}{0pt}",
    "\\pgfsetinnerlinewidth{0.4pt}", "\\pgfsetinnerdash{{2pt}{2pt}}{0pt}",
    "\\pgfsetbuttcap", "\\pgfsetroundcap", "\\pgfsetrectcap",
    "\\pgfsetmiterjoin", "\\pgfsetroundjoin", "\\pgfsetbeveljoin",
    "\\pgfsetmiterlimit{10}", "\\pgfsetcolor{}", "\\pgfsetstrokecolor{}",
    "\\pgfsetfillcolor{}", "\\pgfsetstrokeopacity{0.5}",
    "\\pgfsetfillopacity{0.5}", "\\pgfsetblendmode{multiply}",
    "\\pgfsetnonzerorule", "\\pgfseteorule",
    "\\pgfsetarrowsstart{stealth}", "\\pgfsetarrowsend{stealth}",
    "\\pgfsetshortenstart{2pt}", "\\pgfsetshortenend{2pt}",
    "\\pgftransformshift{\\pgfpoint{1cm}{0cm}}",
    "\\pgftransformscale{2}", "\\pgftransformxscale{2}",
    "\\pgftransformyscale{2}", "\\pgftransformrotate{45}",
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
        self.jump_handler = None      # set by the app: line -> canvas jump
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

    def contextMenuEvent(self, ev):
        menu = self.createStandardContextMenu()
        if self.jump_handler is not None:
            menu.addSeparator()
            cur = self.cursorForPosition(ev.pos())
            line = cur.blockNumber()
            act = menu.addAction("⇠ Show element on canvas")
            act.triggered.connect(lambda: self.jump_handler(line))
            menu.addSeparator()
            fr = menu.addAction("Find / Replace…\tCtrl+H")
            fr.triggered.connect(self._replace_dialog)
            c = menu.addAction("Comment lines\tCtrl+T")
            c.triggered.connect(lambda: self._comment_selection(True))
            u = menu.addAction("Uncomment lines\tCtrl+R")
            u.triggered.connect(lambda: self._comment_selection(False))
        menu.exec(ev.globalPos())

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
        ctrl = ev.modifiers() & Qt.KeyboardModifier.ControlModifier
        if self.completer.popup().isVisible() and ev.key() in (
                Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab,
                Qt.Key.Key_Escape):
            ev.ignore()
            return
        if ctrl and ev.key() == Qt.Key.Key_Space:
            self._popup_completions()
            return
        if ctrl and ev.key() == Qt.Key.Key_T:        # comment selection
            self._comment_selection(True)
            return
        if ctrl and ev.key() == Qt.Key.Key_R:        # uncomment selection
            self._comment_selection(False)
            return
        if ctrl and ev.key() == Qt.Key.Key_F:        # find
            self._find_dialog()
            return
        if ctrl and ev.key() == Qt.Key.Key_H:        # search & replace
            self._replace_dialog()
            return
        if ev.key() == Qt.Key.Key_F3:                # find next / previous
            self._find_next(backwards=bool(
                ev.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            return
        super().keyPressEvent(ev)
        # auto-suggest while typing: commands after '\\' AND plain
        # option/tag words (2+ letters)
        prefix = self._word_under_cursor()
        if ev.text() and (prefix.startswith("\\") and len(prefix) >= 2
                          or (not prefix.startswith("\\")
                              and len(prefix) >= 2)):
            self._popup_completions()
        elif self.completer.popup().isVisible():
            if len(prefix) < 1:
                self.completer.popup().hide()
            else:
                self.completer.setCompletionPrefix(prefix)

    # -- comment / uncomment selected lines (Ctrl+T / Ctrl+R) ---------------
    def _comment_selection(self, add: bool):
        tc = self.textCursor()
        doc = self.document()
        start, end = tc.selectionStart(), tc.selectionEnd()
        first = doc.findBlock(start)
        last = doc.findBlock(end if end == start else end - 1)
        tc.beginEditBlock()
        block = first
        while block.isValid():
            text = block.text()
            cur = QTextCursor(block)
            if add:
                if text.strip():
                    cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                    cur.insertText("% ")
            else:
                stripped = text.lstrip()
                if stripped.startswith("%"):
                    lead = len(text) - len(stripped)
                    drop = 1
                    if stripped[1:2] == " ":
                        drop = 2
                    cur.setPosition(block.position() + lead)
                    cur.setPosition(block.position() + lead + drop,
                                    QTextCursor.MoveMode.KeepAnchor)
                    cur.removeSelectedText()
            if block == last:
                break
            block = block.next()
        tc.endEditBlock()

    # -- search & replace (Ctrl+H) --------------------------------------------
    def _replace_dialog(self):
        from PyQt6.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                                     QHBoxLayout, QPushButton, QVBoxLayout,
                                     QLabel, QCheckBox)
        dlg = QDialog(self)
        dlg.setWindowTitle("Find && Replace")
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        find_e = QLineEdit(getattr(self, "_find_q", ""))
        repl_e = QLineEdit(getattr(self, "_repl_q", ""))
        case_cb = QCheckBox("Match case")
        form.addRow("Find:", find_e)
        form.addRow("Replace with:", repl_e)
        form.addRow("", case_cb)
        lay.addLayout(form)
        info = QLabel("")
        info.setStyleSheet("color:#6b7280; font-size:11px;")
        lay.addWidget(info)
        row = QHBoxLayout()
        b_find = QPushButton("Find next")
        b_repl = QPushButton("Replace")
        b_all = QPushButton("Replace all")
        b_close = QPushButton("Close")
        for b in (b_find, b_repl, b_all, b_close):
            row.addWidget(b)
        lay.addLayout(row)

        from PyQt6.QtGui import QTextDocument

        def flags():
            return (QTextDocument.FindFlag.FindCaseSensitively
                    if case_cb.isChecked() else QTextDocument.FindFlag(0))

        def do_find():
            self._find_q = find_e.text()
            if not self._find_q:
                return False
            if not self.find(self._find_q, flags()):
                cur = self.textCursor()
                cur.movePosition(QTextCursor.MoveOperation.Start)
                self.setTextCursor(cur)
                if not self.find(self._find_q, flags()):
                    info.setText("Not found.")
                    return False
            info.setText("")
            return True

        def do_replace():
            self._repl_q = repl_e.text()
            tc = self.textCursor()
            if tc.hasSelection() and (
                    tc.selectedText() == find_e.text()
                    or (not case_cb.isChecked()
                        and tc.selectedText().lower()
                        == find_e.text().lower())):
                tc.insertText(repl_e.text())
            do_find()

        def do_all():
            self._find_q, self._repl_q = find_e.text(), repl_e.text()
            if not self._find_q:
                return
            tc = self.textCursor()
            tc.movePosition(QTextCursor.MoveOperation.Start)
            self.setTextCursor(tc)
            n = 0
            cur = self.textCursor()
            cur.beginEditBlock()
            while self.find(self._find_q, flags()):
                self.textCursor().insertText(repl_e.text())
                n += 1
                if n > 10000:
                    break
            cur.endEditBlock()
            info.setText(f"Replaced {n} occurrence(s).")

        b_find.clicked.connect(do_find)
        b_repl.clicked.connect(do_replace)
        b_all.clicked.connect(do_all)
        b_close.clicked.connect(dlg.close)
        find_e.returnPressed.connect(do_find)
        dlg.show()

    # -- find (Ctrl+F, F3 / Shift+F3) ---------------------------------------
    def _find_dialog(self):
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Find", "Find text:",
                                        text=getattr(self, "_find_q", ""))
        if ok and text:
            self._find_q = text
            self._find_next()

    def _find_next(self, backwards=False):
        q = getattr(self, "_find_q", "")
        if not q:
            return
        from PyQt6.QtGui import QTextDocument
        flags = QTextDocument.FindFlag.FindBackward if backwards \
            else QTextDocument.FindFlag(0)
        if not self.find(q, flags):
            cur = self.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End if backwards
                             else QTextCursor.MoveOperation.Start)
            self.setTextCursor(cur)
            self.find(q, flags)

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
