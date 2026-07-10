"""Dialogs: preamble / package manager for the standalone document."""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QListWidget, QPushButton, QCheckBox,
                             QDialogButtonBox, QLabel, QPlainTextEdit,
                             QGroupBox, QGridLayout)

from .elements import TikzDocument

COMMON_LIBRARIES = ["arrows.meta", "shapes.geometric", "shapes.callouts",
                    "positioning", "calc", "patterns", "trees",
                    "decorations.pathmorphing", "decorations.markings",
                    "fit", "backgrounds", "matrix", "mindmap", "automata"]

COMMON_PACKAGES = ["amsmath", "amssymb", "graphicx", "xcolor",
                   "pgfplots", "siunitx", "bm"]


class PreambleDialog(QDialog):
    """Manage \\documentclass options, \\usepackage list and TikZ libraries."""

    def __init__(self, doc: TikzDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle("Document setup — packages && libraries")
        self.resize(560, 560)
        lay = QVBoxLayout(self)

        # document class ------------------------------------------------
        form = QFormLayout()
        self.cls_opts = QLineEdit(doc.doc_class_options)
        form.addRow(QLabel("\\documentclass[<b>options</b>]{standalone}:"),
                    self.cls_opts)
        lay.addLayout(form)

        # packages ---------------------------------------------------------
        pk_box = QGroupBox("LaTeX packages (\\usepackage{...})")
        pk_lay = QVBoxLayout(pk_box)
        self.pkg_list = QListWidget()
        self.pkg_list.addItems(doc.packages)
        pk_lay.addWidget(self.pkg_list)
        row = QHBoxLayout()
        self.pkg_edit = QLineEdit()
        self.pkg_edit.setPlaceholderText("package name, e.g. amsmath")
        add = QPushButton("Add"); rem = QPushButton("Remove selected")
        add.clicked.connect(self._add_pkg)
        self.pkg_edit.returnPressed.connect(self._add_pkg)
        rem.clicked.connect(lambda: [self.pkg_list.takeItem(
            self.pkg_list.row(i)) for i in self.pkg_list.selectedItems()])
        row.addWidget(self.pkg_edit); row.addWidget(add); row.addWidget(rem)
        pk_lay.addLayout(row)
        quick = QHBoxLayout()
        quick.addWidget(QLabel("Quick add:"))
        for p in COMMON_PACKAGES:
            b = QPushButton(p)
            b.setFlat(True)
            b.setStyleSheet("color:#1d4ed8; text-decoration:underline;")
            b.clicked.connect(lambda _=False, name=p: self._quick_pkg(name))
            quick.addWidget(b)
        quick.addStretch()
        pk_lay.addLayout(quick)
        lay.addWidget(pk_box)

        # tikz libraries -----------------------------------------------------
        lib_box = QGroupBox("TikZ libraries (\\usetikzlibrary{...})")
        grid = QGridLayout(lib_box)
        self.lib_checks = {}
        for i, lib in enumerate(COMMON_LIBRARIES):
            cb = QCheckBox(lib)
            cb.setChecked(lib in doc.tikz_libraries)
            self.lib_checks[lib] = cb
            grid.addWidget(cb, i // 3, i % 3)
        self.lib_extra = QLineEdit(
            ",".join(l for l in doc.tikz_libraries
                     if l not in COMMON_LIBRARIES))
        self.lib_extra.setPlaceholderText("other libraries, comma separated")
        grid.addWidget(self.lib_extra, len(COMMON_LIBRARIES) // 3 + 1, 0, 1, 3)
        lay.addWidget(lib_box)

        # extra preamble ------------------------------------------------------
        ex_box = QGroupBox("Extra preamble (macros, \\definecolor, pgfplots setup …)")
        ex_lay = QVBoxLayout(ex_box)
        self.extra = QPlainTextEdit(doc.extra_preamble)
        self.extra.setMaximumHeight(90)
        ex_lay.addWidget(self.extra)
        lay.addWidget(ex_box)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _add_pkg(self):
        name = self.pkg_edit.text().strip()
        if name and not self.pkg_list.findItems(name, 0):
            self.pkg_list.addItem(name)
        self.pkg_edit.clear()

    def _quick_pkg(self, name):
        if not self.pkg_list.findItems(name, 0):
            self.pkg_list.addItem(name)

    def apply(self):
        self.doc.doc_class_options = self.cls_opts.text().strip() or "tikz,border=2mm"
        self.doc.packages = [self.pkg_list.item(i).text()
                             for i in range(self.pkg_list.count())]
        libs = [l for l, cb in self.lib_checks.items() if cb.isChecked()]
        libs += [l.strip() for l in self.lib_extra.text().split(",") if l.strip()]
        self.doc.tikz_libraries = libs
        self.doc.extra_preamble = self.extra.toPlainText()
