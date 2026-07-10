"""TikZ Studio main window."""

import os
import re
import shutil
import subprocess

from PyQt6.QtCore import Qt, QTimer, QThread, QSize
from PyQt6.QtGui import (QAction, QKeySequence, QPixmap, QColor,
                         QActionGroup, QIcon, QPainter, QFont)
from PyQt6.QtWidgets import (QMainWindow, QToolBar, QDockWidget, QLabel,
                             QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTabBar, QFileDialog, QMessageBox, QComboBox,
                             QDoubleSpinBox, QFormLayout, QCheckBox,
                             QScrollArea, QSpinBox, QColorDialog,
                             QPlainTextEdit, QInputDialog, QApplication,
                             QListWidget, QListWidgetItem, QDialog,
                             QDialogButtonBox, QLineEdit, QFormLayout,
                             QToolButton, QMenu)

from .elements import (TikzDocument, Figure, Style, NodeEl, ImageEl, GridEl,
                       ArcEl, RawEl, LibraryEl, GroupEl, TREE_TEMPLATE,
                       CALLOUT_TEMPLATE)
from . import library as libmod
from .library import REGISTRY, LibraryBuilder, compile_custom
from .textformat import parse_format, apply_format, SIZES
from .parser import parse_body, import_tex
from .canvas import Canvas, TOOLS
from .editor import TikzEditor
from .compiler import Compiler
from .dialogs import PreambleDialog

TOOL_LABELS = {
    "select": ("⬚", "Select / move (S)"),
    "line": ("╱", "Line (L) — drag"),
    "arrow": ("→", "Arrow (A) — drag"),
    "rect": ("▭", "Rectangle (R) — drag"),
    "circle": ("◯", "Circle (C) — drag from centre"),
    "ellipse": ("⬭", "Ellipse (E) — drag"),
    "polygon": ("⬠", "Polygon (P) — click vertices, double-click to close"),
    "star": ("★", "Star — drag from centre"),
    "bezier": ("∿", "Bézier curve (B) — drag, then tweak control points in code"),
    "freehand": ("✎", "Freehand (F) — draw"),
    "arc": ("◜", "Arc — drag from centre; edit angles in Properties"),
    "grid": ("▦", "Grid — drag area"),
    "node": ("T", "Text node (N) — click"),
    "image": ("🖼", "Insert image — click position"),
}


def glyph_icon(char: str, color="#1f2937", pt=15) -> QIcon:
    pm = QPixmap(26, 26)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    f = QFont("DejaVu Sans", pt)
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, char)
    p.end()
    return QIcon(pm)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TikZ Studio")
        self.resize(1360, 860)
        self.doc = TikzDocument()
        self.current_fig = 0
        self.file_path = None
        self.base_dir = os.getcwd()
        self._syncing = False
        self.compiler = Compiler()
        self.compiler.finished.connect(self._compile_done)

        self.canvas = Canvas()
        self.canvas.model_changed.connect(self._canvas_changed)
        self.canvas.selection_changed.connect(self._show_properties)
        self.canvas.status.connect(lambda s: self.statusBar().showMessage(s, 4000))
        self.canvas.place_requested.connect(self._place_library_element)
        self.canvas.jump_to_code.connect(self._jump_to_code)
        self._pending_shape = None

        # central widget = figure tab bar + canvas
        central = QWidget(); v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        bar = QHBoxLayout()
        self.fig_tabs = QTabBar()
        self.fig_tabs.setTabsClosable(True)
        self.fig_tabs.currentChanged.connect(self._switch_figure)
        self.fig_tabs.tabCloseRequested.connect(self._close_figure)
        addfig = QPushButton("＋ figure")
        addfig.setToolTip("Add another tikzpicture to this document")
        addfig.clicked.connect(self._add_figure)
        bar.addWidget(self.fig_tabs, 1); bar.addWidget(addfig)
        v.addLayout(bar); v.addWidget(self.canvas, 1)
        self.setCentralWidget(central)

        self._build_toolbar()
        self._build_code_dock()
        self._build_props_dock()
        self._build_palette_dock()
        self._build_preview_dock()
        self._build_menus()
        self._init_library()
        self._refresh_fig_tabs()
        self._push_code_to_editor()
        self.statusBar().showMessage(
            "Draw on the canvas or type TikZ code — they stay in sync. "
            "F5 compiles.", 8000)

        self._code_timer = QTimer(self)
        self._code_timer.setSingleShot(True)
        self._code_timer.setInterval(700)
        self._code_timer.timeout.connect(self._apply_code_to_canvas)

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.setInterval(1200)
        self._auto_timer.timeout.connect(self.compile)

    # ==================================================================
    # UI construction
    # ==================================================================
    def _build_toolbar(self):
        tb = QToolBar("Tools"); tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        group = QActionGroup(self); group.setExclusive(True)
        self.tool_actions = {}
        shortcuts = {"select": "S", "line": "L", "rect": "R",
                     "circle": "C", "ellipse": "E", "polygon": "P",
                     "bezier": "B", "freehand": "F", "node": "N"}
        for tool in TOOLS:
            icon, tip = TOOL_LABELS[tool]
            if tool == "arrow":
                btn = QToolButton()
                btn.setIcon(glyph_icon("→"))
                btn.setToolTip("Arrows — straight (drag) or multipoint "
                               "(dropdown; click waypoints, double-click "
                               "to finish)   [A]")
                btn.setPopupMode(
                    QToolButton.ToolButtonPopupMode.MenuButtonPopup)
                btn.setCheckable(True)
                menu = QMenu(btn)
                a1 = menu.addAction(glyph_icon("→"), "Straight arrow  (A)")
                a2 = menu.addAction(glyph_icon("↝"), "Multipoint arrow")
                a1.triggered.connect(
                    lambda: (btn.setIcon(glyph_icon("→")),
                             self.canvas.set_tool("arrow")))
                a2.triggered.connect(
                    lambda: (btn.setIcon(glyph_icon("↝")),
                             self.canvas.set_tool("multiarrow")))
                btn.setMenu(menu)
                btn.clicked.connect(
                    lambda: self.canvas.set_tool(self._arrow_variant))
                self._arrow_variant = "arrow"
                a1.triggered.connect(
                    lambda: setattr(self, "_arrow_variant", "arrow"))
                a2.triggered.connect(
                    lambda: setattr(self, "_arrow_variant", "multiarrow"))
                arr_short = QAction(self)
                arr_short.setShortcut("A")
                arr_short.triggered.connect(
                    lambda: self.canvas.set_tool("arrow"))
                self.addAction(arr_short)
                tb.addWidget(btn)
                self._arrow_btn = btn
                continue
            act = QAction(glyph_icon(icon), tool.capitalize(), self)
            act.setCheckable(True)
            act.setToolTip(tip + (f"   [{shortcuts[tool]}]"
                                  if tool in shortcuts else ""))
            if tool in shortcuts:
                act.setShortcut(shortcuts[tool])
            act.triggered.connect(
                lambda _=False, t=tool: self.canvas.set_tool(t))
            group.addAction(act); tb.addAction(act)
            self.tool_actions[tool] = act
            if tool == "select":
                act.setChecked(True)
        self.canvas.tool_changed.connect(self._tool_changed_ui)
        tb.addSeparator()

        # scope grouping buttons
        grp = QAction(glyph_icon("⧉"), "Group into scope", self)
        grp.setToolTip("Group the selected elements into a "
                       "\\begin{scope} — move / scale / rotate them "
                       "together   [Ctrl+G]")
        grp.triggered.connect(self.group_selection)
        tb.addAction(grp)
        ung = QAction(glyph_icon("⧈"), "Ungroup scope", self)
        ung.setToolTip("Ungroup the selected scope, baking its transform "
                       "into the elements   [Ctrl+Shift+G]")
        ung.triggered.connect(self.ungroup_selection)
        tb.addAction(ung)
        tb.addSeparator()

        # ONE compile action shared by toolbar and menu (two separate
        # F5 shortcuts made Qt treat the key as ambiguous and drop it)
        self.compile_action = QAction(glyph_icon("▶", "#047857"),
                                      "Compile", self)
        self.compile_action.setShortcut("F5")
        self.compile_action.setToolTip("Compile with pdflatex and show the "
                                       "PDF preview   [F5]")
        self.compile_action.triggered.connect(self.compile)
        tb.addAction(self.compile_action)
        self.auto_cb = QCheckBox("Auto-compile")
        tb.addWidget(self.auto_cb)
        snap = QCheckBox("Snap"); snap.setChecked(True)
        snap.toggled.connect(lambda b: setattr(self.canvas, "snap", b))
        tb.addWidget(snap)
        gridcb = QCheckBox("Canvas grid"); gridcb.setChecked(True)
        gridcb.toggled.connect(self._toggle_grid)
        tb.addWidget(gridcb)
        tb.addWidget(QLabel("  Grid size:"))
        self.grid_spin = QDoubleSpinBox()
        self.grid_spin.setRange(0.05, 5.0)
        self.grid_spin.setSingleStep(0.05)
        self.grid_spin.setDecimals(2)
        self.grid_spin.setValue(0.5)
        self.grid_spin.setSuffix(" cm")
        self.grid_spin.setToolTip("Grid spacing — also the snap step, "
                                  "for precise drawing")
        self.grid_spin.valueChanged.connect(self._set_grid_step)
        tb.addWidget(self.grid_spin)

    def _tool_changed_ui(self, tool):
        if tool in self.tool_actions:
            self.tool_actions[tool].setChecked(True)
        if hasattr(self, "_arrow_btn"):
            self._arrow_btn.setChecked(tool in ("arrow", "multiarrow"))

    def _toggle_grid(self, b):
        self.canvas.show_grid = b
        self.canvas.viewport().update()

    def _set_grid_step(self, v):
        self.canvas.grid_step = v
        self.canvas.viewport().update()
        self.statusBar().showMessage(
            f"Grid / snap step: {v:g} cm", 3000)

    def _build_code_dock(self):
        self.editor = TikzEditor()
        self.editor.textChanged.connect(self._editor_changed)
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        top.addWidget(QLabel("Edit:"))
        self.code_mode = "figure"
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Current figure body", "Whole document"])
        self.mode_combo.setToolTip(
            "Figure body: two-way sync with the canvas.\n"
            "Whole document: full .tex file editing — preamble, packages "
            "and every figure, still live-synced.")
        self.mode_combo.currentIndexChanged.connect(self._code_mode_changed)
        top.addWidget(self.mode_combo, 1)
        lay.addLayout(top)
        hint = QLabel("Two-way sync. Ctrl+Wheel scrubs numbers · Ctrl+Space "
                      "completes · Ctrl+T/Ctrl+R (un)comment lines · "
                      "Ctrl+F find (F3 next) · Ctrl+Z undo.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6b7280; font-size:11px;")
        lay.addWidget(hint); lay.addWidget(self.editor, 1)
        self.editor.jump_handler = self._jump_to_canvas
        dock = QDockWidget("TikZ code", self)
        dock.setWidget(w)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.code_dock = dock

    def _build_props_dock(self):
        w = QWidget(); self.props_form = QFormLayout(w)
        self.props_widgets = {}

        self.p_draw = QPushButton("stroke")
        self.p_draw.clicked.connect(lambda: self._pick_color("draw"))
        self.p_fill = QPushButton("fill  (right-click = none)")
        self.p_fill.clicked.connect(lambda: self._pick_color("fill"))
        self.p_fill.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.p_fill.customContextMenuRequested.connect(
            lambda _: self._set_style("fill", ""))
        self.p_lw = QDoubleSpinBox(); self.p_lw.setRange(0.05, 10); self.p_lw.setSingleStep(0.2)
        self.p_lw.setValue(0.4); self.p_lw.setSuffix(" pt")
        self.p_lw.valueChanged.connect(lambda v: self._set_style("line_width", v))
        self.p_dash = QComboBox(); self.p_dash.addItems(["solid", "dashed", "dotted"])
        self.p_dash.currentTextChanged.connect(lambda t: self._set_style("dash", t))
        self.p_arrow = QComboBox()
        self.p_arrow.addItems(["", "->", "<-", "<->", "-Stealth",
                               "Stealth-Stealth", "-Latex", "Latex-Latex"])
        self.p_arrow.setToolTip("Arrow tips: -> classic open, "
                                "-Stealth filled dart, -Latex filled triangle")
        self.p_arrow.currentTextChanged.connect(lambda t: self._set_style("arrows", t))
        self.p_op = QDoubleSpinBox(); self.p_op.setRange(0.05, 1.0)
        self.p_op.setSingleStep(0.1); self.p_op.setValue(1.0)
        self.p_op.valueChanged.connect(lambda v: self._set_style("opacity", v))

        self.props_form.addRow("Stroke colour", self.p_draw)
        self.props_form.addRow("Fill colour", self.p_fill)
        self.props_form.addRow("Line width", self.p_lw)
        self.props_form.addRow("Dash", self.p_dash)
        self.props_form.addRow("Arrow tips", self.p_arrow)
        self.props_form.addRow("Opacity", self.p_op)
        self.p_fop = QDoubleSpinBox(); self.p_fop.setRange(0.0, 1.0)
        self.p_fop.setSingleStep(0.1); self.p_fop.setValue(1.0)
        self.p_fop.setToolTip("Transparency of the fill only "
                              "(TikZ 'fill opacity')")
        self.p_fop.valueChanged.connect(
            lambda v: self._set_style("fill_opacity", v))
        self.props_form.addRow("Fill opacity", self.p_fop)

        # LaTeX text formatting for the selected node
        fmt_row = QHBoxLayout()
        self.p_bold = QPushButton("B"); self.p_bold.setCheckable(True)
        self.p_bold.setStyleSheet("font-weight:bold;")
        self.p_italic = QPushButton("I"); self.p_italic.setCheckable(True)
        self.p_italic.setStyleSheet("font-style:italic;")
        self.p_under = QPushButton("U"); self.p_under.setCheckable(True)
        self.p_under.setStyleSheet("text-decoration:underline;")
        for b in (self.p_bold, self.p_italic, self.p_under):
            b.setMaximumWidth(30)
            b.toggled.connect(self._apply_text_format)
        self.p_tcolor = QPushButton("A")
        self.p_tcolor.setMaximumWidth(30)
        self.p_tcolor.setToolTip("Text colour (\\textcolor)")
        self.p_tcolor.clicked.connect(self._pick_text_color)
        fmt_row.addWidget(self.p_bold); fmt_row.addWidget(self.p_italic)
        fmt_row.addWidget(self.p_under); fmt_row.addWidget(self.p_tcolor)
        fmt_row.addStretch()
        fw = QWidget(); fw.setLayout(fmt_row)
        self.props_form.addRow("Text format", fw)
        self.p_tsize = QComboBox(); self.p_tsize.addItems(SIZES)
        self.p_tsize.setCurrentText("normalsize")
        self.p_tsize.currentTextChanged.connect(
            lambda _: self._apply_text_format())
        self.props_form.addRow("Text size", self.p_tsize)

        self.p_star_n = QSpinBox(); self.p_star_n.setRange(3, 12); self.p_star_n.setValue(5)
        self.p_star_n.valueChanged.connect(
            lambda v: setattr(self.canvas, "star_points", v))
        self.props_form.addRow("Star points", self.p_star_n)

        # contextual (selection) fields
        self.p_a1 = QDoubleSpinBox(); self.p_a1.setRange(-360, 360)
        self.p_a2 = QDoubleSpinBox(); self.p_a2.setRange(-360, 360)
        for sb, attr in ((self.p_a1, "a1"), (self.p_a2, "a2")):
            sb.valueChanged.connect(lambda v, a=attr: self._set_attr(a, v))
        self.props_form.addRow("Arc start °", self.p_a1)
        self.props_form.addRow("Arc end °", self.p_a2)
        self.p_step = QDoubleSpinBox(); self.p_step.setRange(0.05, 10)
        self.p_step.setSingleStep(0.25); self.p_step.setValue(0.5)
        self.p_step.valueChanged.connect(lambda v: self._set_attr("step", v))
        self.props_form.addRow("Grid step", self.p_step)
        self.p_imgw = QDoubleSpinBox(); self.p_imgw.setRange(0.2, 30)
        self.p_imgw.setValue(3.0); self.p_imgw.setSuffix(" cm")
        self.p_imgw.valueChanged.connect(lambda v: self._set_attr("width", v))
        self.props_form.addRow("Image width", self.p_imgw)
        self.p_imgh = QDoubleSpinBox(); self.p_imgh.setRange(0.0, 30)
        self.p_imgh.setValue(0.0); self.p_imgh.setSuffix(" cm")
        self.p_imgh.setSpecialValueText("auto")
        self.p_imgh.setToolTip("graphicx height= (0 = auto from width)")
        self.p_imgh.valueChanged.connect(lambda v: self._set_attr("height", v))
        self.props_form.addRow("Image height", self.p_imgh)
        self.p_scale = QDoubleSpinBox(); self.p_scale.setRange(0.05, 20)
        self.p_scale.setSingleStep(0.1); self.p_scale.setValue(1.0)
        self.p_scale.setToolTip("Scale of the selected scope group")
        self.p_scale.valueChanged.connect(lambda v: self._set_attr("s", v))
        self.props_form.addRow("Group scale", self.p_scale)
        self.p_grot = QDoubleSpinBox(); self.p_grot.setRange(-360, 360)
        self.p_grot.valueChanged.connect(lambda v: self._set_attr("rot", v))
        self.props_form.addRow("Group rotate °", self.p_grot)
        self.p_gxs = QDoubleSpinBox(); self.p_gxs.setRange(-20, 20)
        self.p_gxs.setValue(1.0); self.p_gxs.setSingleStep(0.1)
        self.p_gxs.setToolTip("xscale (negative mirrors horizontally)")
        self.p_gxs.valueChanged.connect(lambda v: self._set_attr("xs", v))
        self.props_form.addRow("Group xscale", self.p_gxs)
        self.p_gys = QDoubleSpinBox(); self.p_gys.setRange(-20, 20)
        self.p_gys.setValue(1.0); self.p_gys.setSingleStep(0.1)
        self.p_gys.setToolTip("yscale (negative mirrors vertically)")
        self.p_gys.valueChanged.connect(lambda v: self._set_attr("ys", v))
        self.props_form.addRow("Group yscale", self.p_gys)

        self.sel_label = QLabel("New shapes use these style settings.\n"
                                "Select one element to edit it.")
        self.sel_label.setWordWrap(True)
        self.sel_label.setStyleSheet("color:#6b7280;")
        self.props_form.addRow(self.sel_label)

        scroll = QScrollArea(); scroll.setWidget(w); scroll.setWidgetResizable(True)
        dock = QDockWidget("Properties", self)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._show_properties(None)

    def _build_preview_dock(self):
        w = QWidget(); lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.page_combo = QComboBox()
        self.page_combo.currentIndexChanged.connect(self._show_page)
        top.addWidget(QLabel("Page:")); top.addWidget(self.page_combo)
        top.addStretch()
        self.compile_state = QLabel("not compiled")
        top.addWidget(self.compile_state)
        lay.addLayout(top)
        self.preview_label = QLabel("Press F5 to compile the real LaTeX preview.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background:#e5e7eb;")
        sc = QScrollArea(); sc.setWidget(self.preview_label); sc.setWidgetResizable(True)
        lay.addWidget(sc, 1)
        self.log_view = QPlainTextEdit(); self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(110)
        self.log_view.setStyleSheet("font-family:monospace; font-size:11px;")
        lay.addWidget(self.log_view)
        dock = QDockWidget("PDF preview && log", self)
        dock.setWidget(w)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.tabifyDockWidget(self.code_dock, dock)
        self.code_dock.raise_()
        self._pages = []

    def _build_menus(self):
        m = self.menuBar()
        f = m.addMenu("&File")
        f.addAction(self._act("New document", "Ctrl+N", self._new_doc))
        f.addAction(self._act("Open .tex…", "Ctrl+O", self.open_tex))
        f.addAction(self._act("Save .tex", "Ctrl+S", self.save_tex))
        f.addAction(self._act("Save .tex as…", "Ctrl+Shift+S",
                              lambda: self.save_tex(True)))
        f.addSeparator()
        f.addAction(self._act("Export PDF…", "Ctrl+E", self.export_pdf))
        f.addAction(self._act("Export PNG…", "Ctrl+Shift+E", self.export_png))
        f.addSeparator()
        f.addAction(self._act("Quit", "Ctrl+Q", self.close))

        e = m.addMenu("&Edit")
        e.addAction(self._act("Undo", "Ctrl+Z", self.undo))
        e.addAction(self._act("Redo", "Ctrl+Shift+Z", self.redo))
        e.addSeparator()
        e.addAction(self._act("Comment lines (editor)", "Ctrl+T",
                              lambda: self.editor._comment_selection(True)))
        e.addAction(self._act("Uncomment lines (editor)", "Ctrl+R",
                              lambda: self.editor._comment_selection(False)))
        e.addSeparator()
        e.addAction(self._act("Delete selection", None,
                              self.canvas.delete_selected))
        e.addAction(self._act("Select all", "Ctrl+A",
                              lambda: [i.setSelected(True)
                                       for i in self.canvas.scene().items()]))
        e.addSeparator()
        e.addAction(self._act("Group into scope", "Ctrl+G",
                              self.group_selection))
        e.addAction(self._act("Ungroup scope", "Ctrl+Shift+G",
                              self.ungroup_selection))

        d = m.addMenu("&Document")
        d.addAction(self._act("Packages && libraries…", "Ctrl+P",
                              self.edit_preamble))
        d.addAction(self._act("Figure environment options…", None,
                              self._edit_env_options))
        d.addAction(self._act("View full standalone source", None,
                              self._show_full_source))
        d.addAction(self._act("Rebuild element library", None,
                              lambda: self._start_library_build(force=True)))

        ins = m.addMenu("&Insert")
        ins.addAction(self._act("Tree layout template", None,
                                lambda: self._insert_raw(TREE_TEMPLATE, ["trees"])))
        ins.addAction(self._act("Callout template", None,
                                lambda: self._insert_raw(CALLOUT_TEMPLATE,
                                                         ["shapes.callouts"])))
        ins.addAction(self._act("Image…", None, self._insert_image))

        b = m.addMenu("&Build")
        b.addAction(self.compile_action)

        h = m.addMenu("&Help")
        h.addAction(self._act("About", None, self._about))

    def _act(self, text, shortcut, slot):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(slot)
        return a

    # ==================================================================
    # figures
    # ==================================================================
    def fig(self) -> Figure:
        return self.doc.figures[self.current_fig]

    def _refresh_fig_tabs(self):
        self.fig_tabs.blockSignals(True)
        while self.fig_tabs.count():
            self.fig_tabs.removeTab(0)
        for f in self.doc.figures:
            self.fig_tabs.addTab(f.name)
        self.fig_tabs.setCurrentIndex(self.current_fig)
        self.fig_tabs.blockSignals(False)
        self.canvas.load_figure(self.fig())

    def _add_figure(self):
        self.doc.figures.append(Figure(name=f"figure{len(self.doc.figures)+1}"))
        self.current_fig = len(self.doc.figures) - 1
        self._refresh_fig_tabs()
        self._push_code_to_editor()

    def _close_figure(self, idx):
        if len(self.doc.figures) == 1:
            QMessageBox.information(self, "TikZ Studio",
                                    "A document needs at least one figure.")
            return
        del self.doc.figures[idx]
        self.current_fig = max(0, min(self.current_fig, len(self.doc.figures) - 1))
        self._refresh_fig_tabs()
        self._push_code_to_editor()

    def _switch_figure(self, idx):
        if 0 <= idx < len(self.doc.figures):
            self.current_fig = idx
            self.canvas.load_figure(self.fig())
            self._push_code_to_editor()
            self._push_history()

    # ==================================================================
    # two-way sync
    # ==================================================================
    def _canvas_changed(self):
        self._push_code_to_editor()
        self._push_history()
        if self.auto_cb.isChecked():
            self._auto_timer.start()

    def _push_code_to_editor(self):
        self._syncing = True
        if getattr(self, "code_mode", "figure") == "document":
            self.editor.setPlainText(self.doc.full_document())
        else:
            self.editor.setPlainText(self.fig().body_code())
        self._syncing = False

    def _code_mode_changed(self, idx):
        self._flush_pending_code()
        self.code_mode = "document" if idx == 1 else "figure"
        self._push_code_to_editor()

    def _apply_full_document(self):
        """Whole-document mode: re-import the full .tex from the editor."""
        try:
            doc = import_tex(self.editor.toPlainText())
        except Exception:
            return
        self.doc = doc
        self.current_fig = min(self.current_fig, len(doc.figures) - 1)
        self.fig_tabs.blockSignals(True)
        while self.fig_tabs.count():
            self.fig_tabs.removeTab(0)
        for f in self.doc.figures:
            self.fig_tabs.addTab(f.name)
        self.fig_tabs.setCurrentIndex(self.current_fig)
        self.fig_tabs.blockSignals(False)
        self.canvas.load_figure(self.fig())
        self._push_history()
        self.statusBar().showMessage(
            f"Document re-imported: {len(doc.figures)} figure(s).", 4000)

    def _editor_changed(self):
        if self._syncing:
            return
        self._code_timer.start()
        if self.auto_cb.isChecked():
            self._auto_timer.start()

    def _apply_code_to_canvas(self):
        if getattr(self, "code_mode", "figure") == "document":
            self._apply_full_document()
            return
        self.fig().elements = parse_body(self.editor.toPlainText())
        self.canvas.rebuild_scene()
        self._push_history()
        raw = sum(isinstance(e, RawEl) for e in self.fig().elements)
        msg = f"Parsed {len(self.fig().elements)} statement(s)"
        if raw:
            msg += (f" — {raw} kept as raw TikZ (compiles fine, "
                    "not editable on canvas)")
        self.statusBar().showMessage(msg, 5000)

    # ==================================================================
    # properties
    # ==================================================================
    def _current_style_target(self):
        sel = self.canvas.selected_elements()
        return sel[0].style if sel else self.canvas.default_style

    def _set_style(self, attr, value):
        if self._syncing:
            return
        st = self._current_style_target()
        setattr(st, attr, value)
        if self.canvas.selected_elements():
            self.canvas.refresh_selected()
            self._push_code_to_editor()
        self._paint_color_buttons(st)

    def _set_attr(self, attr, value):
        if self._syncing:
            return
        sel = self.canvas.selected_elements()
        if sel and hasattr(sel[0], attr):
            setattr(sel[0], attr, value)
            self.canvas.refresh_selected()
            self._push_code_to_editor()

    def _pick_color(self, which):
        st = self._current_style_target()
        cur = getattr(st, which) or "black"
        c = QColorDialog.getColor(QColor(cur.split("!")[0]) if QColor(
            cur.split("!")[0]).isValid() else QColor("black"), self)
        if c.isValid():
            tikz = f"{{rgb,255:red,{c.red()};green,{c.green()};blue,{c.blue()}}}"
            named = {"#000000": "black", "#ff0000": "red", "#00ff00": "green",
                     "#0000ff": "blue", "#ffffff": "white", "#ffff00": "yellow",
                     "#00ffff": "cyan", "#ff00ff": "magenta",
                     "#ffa500": "orange", "#808080": "gray"}
            tikz = named.get(c.name(), tikz)
            self._set_style(which, tikz)

    def _paint_color_buttons(self, st: Style):
        from .canvas import qcolor
        self.p_draw.setStyleSheet(
            f"background:{qcolor(st.draw or 'black').name()}; color:white;")
        f = qcolor(st.fill) if st.fill else QColor("#ffffff")
        self.p_fill.setStyleSheet(f"background:{f.name()};")

    def _show_properties(self, element):
        self._syncing = True
        st = element.style if element else self.canvas.default_style
        self.p_lw.setValue(st.line_width)
        self.p_dash.setCurrentText(st.dash)
        self.p_arrow.setCurrentText(st.arrows)
        self.p_op.setValue(st.opacity)
        self.p_fop.setValue(st.fill_opacity)
        is_node = isinstance(element, NodeEl)
        for wdg in (self.p_bold, self.p_italic, self.p_under,
                    self.p_tcolor, self.p_tsize):
            wdg.setEnabled(is_node)
        if is_node:
            fmt = parse_format(element.text)
            self.p_bold.setChecked(fmt.bold)
            self.p_italic.setChecked(fmt.italic)
            self.p_under.setChecked(fmt.underline)
            self.p_tsize.setCurrentText(fmt.size)
        self._paint_color_buttons(st)
        is_arc = isinstance(element, ArcEl)
        is_grid = isinstance(element, GridEl)
        is_img = isinstance(element, ImageEl)
        is_grp = isinstance(element, GroupEl)
        self.p_a1.setEnabled(is_arc); self.p_a2.setEnabled(is_arc)
        self.p_step.setEnabled(is_grid); self.p_imgw.setEnabled(is_img)
        self.p_imgh.setEnabled(is_img)
        self.p_scale.setEnabled(is_grp)
        for wdg in (self.p_grot, self.p_gxs, self.p_gys):
            wdg.setEnabled(is_grp)
        if is_grp:
            self.p_scale.setValue(element.s)
            self.p_grot.setValue(element.rot)
            self.p_gxs.setValue(element.xs)
            self.p_gys.setValue(element.ys)
        if is_arc:
            self.p_a1.setValue(element.a1); self.p_a2.setValue(element.a2)
        if is_grid:
            self.p_step.setValue(element.step)
        if is_img:
            self.p_imgw.setValue(element.width)
            self.p_imgh.setValue(element.height)
        if element is None:
            self.sel_label.setText("New shapes use these style settings.\n"
                                   "Select one element to edit it.")
        elif isinstance(element, GroupEl):
            self.sel_label.setText(
                f"Selected: scope group ({len(element.children)} elements)\n"
                "Drag to move all together; 'Group scale' resizes the whole "
                "group. Ctrl+Shift+G ungroups (bakes the transform).")
        else:
            self.sel_label.setText(
                f"Selected: {type(element).__name__.replace('El','')}\n"
                "Drag the square handles to reshape. Arrow keys nudge "
                "(plain 0.05 cm, Shift = one grid cell, Ctrl = 0.01 cm).")
        self._syncing = False

    # ==================================================================
    # jump: canvas element <-> code line
    # ==================================================================
    def _element_line_spans(self):
        spans, ln = [], 0
        for el in self.fig().elements:
            n = el.to_tikz().count("\n") + 1
            spans.append((el, ln, n))
            ln += n
        return spans

    def _jump_to_code(self, element):
        if getattr(self, "code_mode", "figure") == "document":
            self.mode_combo.setCurrentIndex(0)     # jump works on figure body
        for el, start, n in self._element_line_spans():
            if el is element:
                from PyQt6.QtGui import QTextCursor
                block = self.editor.document().findBlockByNumber(start)
                cur = QTextCursor(block)
                cur.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                                 QTextCursor.MoveMode.KeepAnchor)
                for _ in range(n - 1):
                    cur.movePosition(QTextCursor.MoveOperation.Down,
                                     QTextCursor.MoveMode.KeepAnchor)
                    cur.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                                     QTextCursor.MoveMode.KeepAnchor)
                self.editor.setTextCursor(cur)
                self.editor.setFocus()
                self.code_dock.raise_()
                self.statusBar().showMessage(
                    f"Code line {start + 1}: "
                    f"{type(element).__name__.replace('El', '')}", 4000)
                return
        self.statusBar().showMessage("Element not found in this figure.", 3000)

    def _jump_to_canvas(self, line: int):
        if getattr(self, "code_mode", "figure") == "document":
            self.statusBar().showMessage(
                "Switch to 'Current figure body' mode to jump to elements.",
                4000)
            return
        self._flush_pending_code()
        for el, start, n in self._element_line_spans():
            if start <= line < start + n:
                if isinstance(el, RawEl):
                    self.statusBar().showMessage(
                        "That statement is raw TikZ — it compiles but has "
                        "no canvas element.", 4000)
                    return
                scene = self.canvas.scene()
                scene.clearSelection()
                from .canvas import ElementItem
                for it in scene.items():
                    if isinstance(it, ElementItem) and it.element is el:
                        it.setSelected(True)
                        self.canvas.centerOn(it)
                        self.canvas.setFocus()
                        self.statusBar().showMessage(
                            f"Selected {type(el).__name__.replace('El','')} "
                            "on canvas.", 3000)
                        return
        self.statusBar().showMessage("No element on that line.", 3000)

    # ==================================================================
    # node text formatting (bold / italic / underline / colour / size)
    # ==================================================================
    def _selected_node(self):
        sel = self.canvas.selected_elements()
        return sel[0] if len(sel) == 1 and isinstance(sel[0], NodeEl) else None

    def _apply_text_format(self):
        if self._syncing:
            return
        n = self._selected_node()
        if n is None:
            return
        fmt = parse_format(n.text)
        fmt.bold = self.p_bold.isChecked()
        fmt.italic = self.p_italic.isChecked()
        fmt.underline = self.p_under.isChecked()
        fmt.size = self.p_tsize.currentText()
        n.text = apply_format(fmt)
        self.canvas.refresh_selected()
        self._push_code_to_editor()
        self._push_history()

    def _pick_text_color(self):
        n = self._selected_node()
        if n is None:
            self.statusBar().showMessage(
                "Select a text node to set its colour.", 3000)
            return
        fmt = parse_format(n.text)
        c = QColorDialog.getColor(QColor(fmt.color.split("!")[0])
                                  if fmt.color else QColor("black"), self)
        if not c.isValid():
            return
        named = {"#000000": "", "#ff0000": "red", "#00ff00": "green",
                 "#0000ff": "blue", "#ffffff": "white",
                 "#ffff00": "yellow", "#00ffff": "cyan",
                 "#ff00ff": "magenta", "#ff8000": "orange",
                 "#808080": "gray"}
        fmt.color = named.get(
            c.name(),
            f"{{rgb,255:red,{c.red()};green,{c.green()};blue,{c.blue()}}}")
        n.text = apply_format(fmt)
        self.canvas.refresh_selected()
        self._push_code_to_editor()
        self._push_history()

    # ==================================================================
    # undo / redo (canvas-level history; editor has its own stack)
    # ==================================================================
    def _push_history(self):
        fig = self.fig()
        if not hasattr(fig, "_hist"):
            fig._hist, fig._hpos = [], -1
        code = fig.body_code()
        if fig._hpos >= 0 and fig._hist[fig._hpos] == code:
            return
        fig._hist = fig._hist[:fig._hpos + 1]
        fig._hist.append(code)
        if len(fig._hist) > 200:
            fig._hist.pop(0)
        fig._hpos = len(fig._hist) - 1

    def _restore_history(self, code: str):
        fig = self.fig()
        fig.elements = parse_body(code)
        self.canvas.rebuild_scene()
        self._syncing = True
        self.editor.setPlainText(code)
        self._syncing = False

    def undo(self):
        if self.editor.hasFocus():
            self.editor.undo()
            return
        fig = self.fig()
        if hasattr(fig, "_hist") and fig._hpos > 0:
            fig._hpos -= 1
            self._restore_history(fig._hist[fig._hpos])
            self.statusBar().showMessage(
                f"Undo ({fig._hpos + 1}/{len(fig._hist)})", 3000)
        else:
            self.statusBar().showMessage("Nothing to undo.", 2000)

    def redo(self):
        if self.editor.hasFocus():
            self.editor.redo()
            return
        fig = self.fig()
        if hasattr(fig, "_hist") and fig._hpos < len(fig._hist) - 1:
            fig._hpos += 1
            self._restore_history(fig._hist[fig._hpos])
            self.statusBar().showMessage(
                f"Redo ({fig._hpos + 1}/{len(fig._hist)})", 3000)
        else:
            self.statusBar().showMessage("Nothing to redo.", 2000)

    # ==================================================================
    # grouping (scopes)
    # ==================================================================
    def group_selection(self):
        sel = self.canvas.selected_elements()
        if len(sel) < 2:
            self.statusBar().showMessage(
                "Select two or more elements to group into a scope.", 4000)
            return
        keep, children = [], []
        for el in self.fig().elements:
            (children if el in sel else keep).append(el)
        idx = min(self.fig().elements.index(el) for el in children)
        g = GroupEl(children=children)
        keep.insert(min(idx, len(keep)), g)
        self.fig().elements = keep
        self.canvas.rebuild_scene()
        self._push_code_to_editor()
        self.statusBar().showMessage(
            f"Grouped {len(children)} elements into a scope — drag to move "
            "them together; set Scale in Properties.", 6000)

    def ungroup_selection(self):
        sel = self.canvas.selected_elements()
        if len(sel) != 1 or not isinstance(sel[0], GroupEl):
            self.statusBar().showMessage("Select one scope to ungroup.", 4000)
            return
        g = sel[0]
        if abs(g.rot) > 1e-9 or abs(g.xs - g.ys) > 1e-9:
            self.statusBar().showMessage(
                "Rotated or x/y-scaled scopes can't be baked into plain "
                "coordinates — set rotate=0 and xscale=yscale first.", 6000)
            return
        idx = self.fig().elements.index(g)
        expanded, kept_raw = [], 0
        uni = g.s * g.xs
        for c in g.children:
            if c.bake(uni, g.x, g.y):
                expanded.append(c)
            else:
                expanded.append(c)      # raw child: keep verbatim, untransformed
                kept_raw += 1
        self.fig().elements[idx:idx + 1] = expanded
        self.canvas.rebuild_scene()
        self._push_code_to_editor()
        msg = f"Ungrouped {len(expanded)} elements (scope transform baked in)."
        if kept_raw:
            msg += (f" {kept_raw} raw statement(s) could not be transformed "
                    "and were kept as-is.")
        self.statusBar().showMessage(msg, 6000)

    # ==================================================================
    # element library palette
    # ==================================================================
    def _build_palette_dock(self):
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        self.lib_status = QLabel("Element library")
        self.lib_status.setWordWrap(True)
        self.lib_status.setStyleSheet("color:#6b7280; font-size:11px;")
        lay.addWidget(self.lib_status)
        self.palette = QListWidget()
        self.palette.setViewMode(QListWidget.ViewMode.IconMode)
        self.palette.setIconSize(QSize(46, 46))
        self.palette.setGridSize(QSize(78, 74))
        self.palette.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.palette.setWordWrap(True)
        self.palette.itemClicked.connect(self._palette_clicked)
        lay.addWidget(self.palette, 1)
        row = QHBoxLayout()
        add = QPushButton("＋ Custom element…")
        add.setToolTip("Compile your own TikZ snippet into a reusable "
                       "palette element")
        add.clicked.connect(self._add_custom_element)
        rebuild = QPushButton("↻")
        rebuild.setToolTip("Rebuild the element library (re-compiles all "
                           "thumbnails)")
        rebuild.setMaximumWidth(30)
        rebuild.clicked.connect(lambda: self._start_library_build(force=True))
        row.addWidget(add, 1); row.addWidget(rebuild)
        lay.addLayout(row)
        dock = QDockWidget("Elements", self)
        dock.setWidget(w)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _init_library(self):
        if REGISTRY.load() and any(not s.custom
                                   for s in REGISTRY.shapes.values()):
            self._fill_palette()
        else:
            self._start_library_build()

    def _start_library_build(self, force=False):
        if getattr(self, "_lib_thread", None) and self._lib_thread.isRunning():
            return
        self.lib_status.setText("First run: pre-compiling all library "
                                "elements with pdflatex…")
        self._lib_worker = LibraryBuilder()
        self._lib_thread = QThread()
        self._lib_worker.moveToThread(self._lib_thread)
        self._lib_thread.started.connect(self._lib_worker.run)
        self._lib_worker.progress.connect(
            lambda t: self.lib_status.setText(t))
        self._lib_worker.finished.connect(self._library_built)
        self._lib_thread.start()

    def _library_built(self, ok, err):
        self._lib_thread.quit(); self._lib_thread.wait()
        if ok:
            self.lib_status.setText(
                "Click an element, then click the canvas to place it.")
            self._fill_palette()
        else:
            self.lib_status.setText("Library build failed: " + err[:300])

    def _fill_palette(self):
        from PyQt6.QtGui import QIcon
        self.palette.clear()
        shapes = sorted(REGISTRY.shapes.values(),
                        key=lambda s: (s.custom, s.name))
        for sh in shapes:
            label = ("★ " if sh.custom else "") + sh.name
            it = QListWidgetItem(label)
            if sh.thumb and os.path.exists(sh.thumb):
                it.setIcon(QIcon(sh.thumb))
            it.setToolTip(sh.template)
            it.setData(Qt.ItemDataRole.UserRole, sh.name)
            self.palette.addItem(it)
        if not self.lib_status.text().startswith("Library build failed"):
            self.lib_status.setText(
                f"{len(shapes)} elements — click one, then click the "
                "canvas to place it.")

    def _palette_clicked(self, item):
        name = item.data(Qt.ItemDataRole.UserRole)
        self._pending_shape = REGISTRY.get(name)
        if self._pending_shape:
            self.canvas.set_tool("place")
            self.statusBar().showMessage(
                f"Placing '{name}' — click on the canvas "
                "(Esc / Select tool to cancel).", 6000)

    def _place_library_element(self, x, y):
        sh = self._pending_shape
        if sh is None:
            return
        for lib in sh.libraries:
            if lib not in self.doc.tikz_libraries:
                self.doc.tikz_libraries.append(lib)
        for pkg in sh.packages:
            if pkg not in self.doc.packages:
                self.doc.packages.append(pkg)
        self.fig().elements.append(
            LibraryEl(name=sh.name, template=sh.template, x=x, y=y))
        self.canvas.rebuild_scene()
        self.canvas.set_tool("select")
        self._push_code_to_editor()
        self._push_history()
        if self.auto_cb.isChecked():
            self._auto_timer.start()

    def _add_custom_element(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add custom element (compiled)")
        dlg.resize(560, 460)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        name_e = QLineEdit()
        libs_e = QLineEdit()
        libs_e.setPlaceholderText("e.g. shapes.geometric, decorations.markings")
        pkgs_e = QLineEdit()
        pkgs_e.setPlaceholderText("e.g. pgfplots (optional)")
        form.addRow("Name:", name_e)
        form.addRow("TikZ libraries:", libs_e)
        form.addRow("Packages:", pkgs_e)
        lay.addLayout(form)
        hint = QLabel(
            "TikZ code drawn around (0,0). Use @X@,@Y@ as the anchor, or "
            "leave them out and the code is wrapped in a shifted scope "
            "automatically. The snippet is test-compiled before it is "
            "added to the palette.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6b7280; font-size:11px;")
        lay.addWidget(hint)
        from .editor import TikzEditor
        code_e = TikzEditor()
        code_e.setPlainText(
            "\\draw[fill=blue!30, fill opacity=0.6] (-0.5,-0.5) "
            "rectangle (0.5,0.5);\n"
            "\\draw[red, thick] (-0.5,-0.5) -- (0.5,0.5);")
        lay.addWidget(code_e, 1)
        self._custom_err = QLabel("")
        self._custom_err.setWordWrap(True)
        self._custom_err.setStyleSheet("color:#dc2626; font-size:11px;")
        lay.addWidget(self._custom_err)
        btns = QDialogButtonBox()
        ok_btn = btns.addButton("Compile && add",
                                QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton(QDialogButtonBox.StandardButton.Cancel)
        btns.rejected.connect(dlg.reject)

        def try_add():
            name = name_e.text().strip()
            if not name:
                self._custom_err.setText("Give the element a name.")
                return
            if REGISTRY.get(name) and not REGISTRY.get(name).custom:
                self._custom_err.setText(
                    "That name is used by a built-in element.")
                return
            libs = [l.strip() for l in libs_e.text().split(",") if l.strip()]
            pkgs = [p.strip() for p in pkgs_e.text().split(",") if p.strip()]
            ok_btn.setEnabled(False)
            ok_btn.setText("Compiling…")
            QApplication.processEvents()
            shape, err = compile_custom(name, code_e.toPlainText(),
                                        libs, pkgs,
                                        self.doc.extra_preamble)
            ok_btn.setEnabled(True)
            ok_btn.setText("Compile && add")
            if shape is None:
                self._custom_err.setText(err)
                return
            REGISTRY.add(shape)
            REGISTRY.save()
            self._fill_palette()
            self.statusBar().showMessage(
                f"Custom element '{name}' compiled and added to the "
                "palette.", 6000)
            dlg.accept()

        btns.accepted.connect(try_add)
        lay.addWidget(btns)
        dlg.exec()

    # ==================================================================
    # preamble / insert
    # ==================================================================
    def edit_preamble(self):
        dlg = PreambleDialog(self.doc, self)
        if dlg.exec():
            dlg.apply()
            self.statusBar().showMessage("Preamble updated.", 3000)
            if self.auto_cb.isChecked():
                self._auto_timer.start()

    def _edit_env_options(self):
        text, ok = QInputDialog.getText(
            self, "tikzpicture options",
            "\\begin{tikzpicture}[ … ]:", text=self.fig().env_options)
        if ok:
            self.fig().env_options = text.strip()

    def _show_full_source(self):
        dlg = QPlainTextEdit()
        dlg.setPlainText(self.doc.full_document())
        dlg.setReadOnly(True)
        dlg.setWindowTitle("Full standalone document")
        dlg.resize(700, 600)
        dlg.setWindowFlag(Qt.WindowType.Window)
        dlg.setParent(self, Qt.WindowType.Window)
        dlg.show()

    def _insert_raw(self, code, needed_libs=None):
        for lib in needed_libs or []:
            if lib not in self.doc.tikz_libraries:
                self.doc.tikz_libraries.append(lib)
                self.statusBar().showMessage(
                    f"Added TikZ library '{lib}' to the preamble.", 4000)
        self.fig().elements.append(RawEl(code=code))
        self.canvas.rebuild_scene()
        self._push_code_to_editor()

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert image", self.base_dir or "",
            "Images (*.png *.jpg *.jpeg *.pdf *.eps)")
        if path:
            if "graphicx" not in self.doc.packages:
                self.doc.packages.append("graphicx")
            self.fig().elements.append(
                ImageEl(x=0, y=0, path=self.canvas._relativize(path),
                        width=3.0))
            self.canvas.rebuild_scene()
            self._push_code_to_editor()

    # ==================================================================
    # compile / export / io
    # ==================================================================
    def compile(self):
        if any(isinstance(e, ImageEl) for f in self.doc.figures
               for e in f.elements) and "graphicx" not in self.doc.packages:
            self.doc.packages.append("graphicx")
        self._flush_pending_code()
        if self.compiler.compile(self.doc.full_document()):
            self.compile_state.setText("compiling…")
            self.compile_state.setStyleSheet("color:#b45309;")

    def _flush_pending_code(self):
        if self._code_timer.isActive():
            self._code_timer.stop()
            self._apply_code_to_canvas()

    def _compile_done(self, ok, log, pdf, pages):
        self.log_view.setPlainText(log)
        self._pages = pages
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        self.page_combo.addItems([f"{i+1}" for i in range(len(pages))])
        self.page_combo.blockSignals(False)
        if ok:
            self.compile_state.setText("✓ compiled")
            self.compile_state.setStyleSheet("color:#047857;")
            self._show_page(0)
        else:
            self.compile_state.setText("✗ error — see log")
            self.compile_state.setStyleSheet("color:#dc2626;")
            m = re.search(r"^! (.+)$", log, re.M)
            if m:
                self.statusBar().showMessage(f"LaTeX error: {m.group(1)}", 8000)

    def _show_page(self, idx):
        if 0 <= idx < len(self._pages):
            pm = QPixmap(self._pages[idx])
            self.preview_label.setPixmap(pm)
            self.preview_label.resize(pm.size())

    def export_pdf(self):
        pdf = os.path.join(self.compiler.workdir, "main.pdf")
        if not os.path.exists(pdf):
            QMessageBox.information(self, "Export PDF",
                                    "Compile first (F5), then export.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Export PDF",
                                              "figure.pdf", "PDF (*.pdf)")
        if dest:
            shutil.copy(pdf, dest)
            self.statusBar().showMessage(f"Exported {dest}", 5000)

    def export_png(self):
        pdf = os.path.join(self.compiler.workdir, "main.pdf")
        if not os.path.exists(pdf):
            QMessageBox.information(self, "Export PNG",
                                    "Compile first (F5), then export.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Export PNG",
                                              "figure.png", "PNG (*.png)")
        if not dest:
            return
        dpi, ok = QInputDialog.getInt(self, "PNG resolution", "DPI:",
                                      300, 72, 1200)
        if not ok:
            return
        base = dest[:-4] if dest.endswith(".png") else dest
        try:
            subprocess.run(["pdftoppm", "-png", "-r", str(dpi), pdf, base],
                           check=True, capture_output=True, timeout=120)
            produced = sorted(f for f in os.listdir(os.path.dirname(base) or ".")
                              if f.startswith(os.path.basename(base)))
            if len(produced) == 1:
                src = os.path.join(os.path.dirname(base) or ".", produced[0])
                if src != base + ".png":
                    shutil.move(src, base + ".png")
            self.statusBar().showMessage(
                f"Exported PNG ({len(produced) or 1} page(s)).", 5000)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            QMessageBox.warning(self, "Export PNG",
                                f"pdftoppm failed: {e}\n"
                                "Install poppler-utils.")

    def save_tex(self, save_as=False):
        self._flush_pending_code()
        if save_as or not self.file_path:
            path, _ = QFileDialog.getSaveFileName(self, "Save .tex",
                                                  "figure.tex",
                                                  "LaTeX (*.tex)")
            if not path:
                return
            self.file_path = path
            self._set_base_dir(os.path.dirname(os.path.abspath(path)))
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(self.doc.full_document())
        self.statusBar().showMessage(f"Saved {self.file_path}", 5000)

    def open_tex(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open TikZ / LaTeX file", self.base_dir or "",
            "TikZ / LaTeX (*.tex *.tikz *.pgf *.txt);;All files (*)")
        if not path:
            return
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.doc = import_tex(text)
        self.file_path = path
        self._set_base_dir(os.path.dirname(os.path.abspath(path)))
        self.current_fig = 0
        self._refresh_fig_tabs()
        self._push_code_to_editor()
        n_raw = sum(isinstance(e, RawEl) for f in self.doc.figures
                    for e in f.elements)
        msg = (f"Imported {len(self.doc.figures)} figure(s) from "
               f"{os.path.basename(path)}.")
        if n_raw:
            msg += f" {n_raw} statement(s) kept as raw TikZ."
        self.statusBar().showMessage(msg, 8000)

    def _set_base_dir(self, folder: str):
        """Make the .tex file's folder the working directory of the figure,
        so \\includegraphics can use relative paths."""
        if not folder or not os.path.isdir(folder):
            return
        self.base_dir = folder
        try:
            os.chdir(folder)
        except OSError:
            pass
        self.canvas.base_dir = folder
        self.canvas.clear_pixmap_cache()
        self.compiler.base_dir = folder
        self.canvas.viewport().update()
        self.statusBar().showMessage(
            f"Working folder: {folder} — images there can be referenced "
            "with relative paths.", 6000)

    def _new_doc(self):
        if QMessageBox.question(
                self, "New document",
                "Discard the current document?") == QMessageBox.StandardButton.Yes:
            self.doc = TikzDocument()
            self.file_path = None
            self.current_fig = 0
            self._refresh_fig_tabs()
            self._push_code_to_editor()

    def _about(self):
        QMessageBox.about(
            self, "TikZ Studio",
            "<b>TikZ Studio 1.0</b><br>"
            "A WYSIWYG TikZ diagram editor with live two-way code sync.<br>"
            "Draw shapes visually or write TikZ directly — export to "
            "PDF/PNG via pdflatex.<br><br>"
            "Requires: texlive (standalone, tikz), poppler-utils.")


def main():
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("TikZ Studio")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
