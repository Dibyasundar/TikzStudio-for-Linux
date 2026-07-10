"""Interactive drawing canvas (WYSIWYG side of the editor)."""

import math
import os
import re as _re
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import (QPainter, QPen, QBrush, QColor, QPainterPath,
                         QPixmap, QFont, QTransform, QFontMetricsF)
from PyQt6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsItem,
                             QGraphicsPathItem, QGraphicsRectItem,
                             QInputDialog, QFileDialog)

from .mathtext import latex_to_unicode
from .elements import (SCALE, Style, Element, LineEl, RectEl, CircleEl,
                       EllipseEl, PolyEl, BezierEl, PlotEl, ArcEl, GridEl,
                       NodeEl, ImageEl, RawEl, LibraryEl, GroupEl, Figure)

TOOLS = ["select", "line", "arrow", "rect", "circle", "ellipse", "polygon",
         "star", "bezier", "freehand", "arc", "grid", "node", "image"]


# ----------------------------------------------------------------------
# colours
# ----------------------------------------------------------------------
NAMED = {  # xcolor base colours (Qt's SVG names differ, e.g. green)
    "red": "#ff0000", "green": "#00ff00", "blue": "#0000ff",
    "cyan": "#00ffff", "magenta": "#ff00ff", "yellow": "#ffff00",
    "black": "#000000", "white": "#ffffff",
    "gray": "#808080", "grey": "#808080", "darkgray": "#404040",
    "lightgray": "#bfbfbf", "olive": "#808000", "teal": "#008080",
    "violet": "#800080", "purple": "#bf0040", "lime": "#bfff00",
    "orange": "#ff8000", "pink": "#ffbfbf", "brown": "#bf8040"}


def _base_color(tok: str) -> QColor:
    tok = tok.strip()
    m = _re.match(r"\{?rgb,255:red,(\d+);green,(\d+);blue,(\d+)\}?", tok)
    if m:
        return QColor(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    c = QColor(NAMED.get(tok, tok))
    return c if c.isValid() else QColor("black")


def qcolor(tikz: str) -> QColor:
    """TikZ/xcolor expression -> QColor, incl. mix chains a!p!b!q!c."""
    if not tikz:
        return QColor(0, 0, 0, 0)
    tikz = tikz.strip()
    m = _re.match(r"\{?rgb,255:red,(\d+);green,(\d+);blue,(\d+)\}?", tikz)
    if m:
        return QColor(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    parts = tikz.split("!")
    c = _base_color(parts[0])
    i = 1
    while i < len(parts):
        try:
            pct = max(0.0, min(100.0, float(parts[i]))) / 100.0
        except ValueError:
            break
        other = (_base_color(parts[i + 1]) if i + 1 < len(parts)
                 else QColor("white"))
        c = QColor(round(c.red() * pct + other.red() * (1 - pct)),
                   round(c.green() * pct + other.green() * (1 - pct)),
                   round(c.blue() * pct + other.blue() * (1 - pct)))
        i += 2
    return c


def qcolor_alpha(tikz: str, alpha: float) -> QColor:
    c = qcolor(tikz)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def to_scene(x: float, y: float) -> QPointF:
    return QPointF(x * SCALE, -y * SCALE)


def from_scene(p: QPointF):
    return p.x() / SCALE, -p.y() / SCALE


# ----------------------------------------------------------------------
# arrowheads — each TikZ tip style gets its own visual
# ----------------------------------------------------------------------
def _tip_kind(token: str) -> str:
    t = token.strip()
    if t in ("<", ">"):
        return "v"
    tl = t.lower()
    if tl == "stealth":
        return "stealth"
    if tl == "latex":
        return "latex"
    return ""


def tip_kinds(arrows: str) -> Tuple[str, str]:
    """'->' -> ('','v');  '<->' -> ('v','v');  '-Stealth' -> ('','stealth')."""
    a = (arrows or "").strip()
    if not a or "-" not in a:
        return "", ""
    left, right = a.split("-", 1)
    return _tip_kind(left), _tip_kind(right)


def head_path(kind: str, tip: QPointF, ang: float,
              lw: float) -> Tuple[QPainterPath, bool]:
    """Build an arrowhead at scene point `tip` pointing along `ang`
    (radians, scene coords).  Returns (path, filled)."""
    L = 9 + lw * 4          # length
    W = 3.5 + lw * 1.6      # half width
    ca, sa = math.cos(ang), math.sin(ang)
    px, py = -sa, ca        # perpendicular
    def pt(back, side):
        return QPointF(tip.x() - back * ca + side * px,
                       tip.y() - back * sa + side * py)
    p = QPainterPath()
    if kind == "v":                       # classic open tip  ->
        p.moveTo(pt(L, W)); p.lineTo(tip); p.lineTo(pt(L, -W))
        return p, False
    if kind == "latex":                   # filled triangle  -Latex
        p.moveTo(tip); p.lineTo(pt(L, W)); p.lineTo(pt(L, -W))
        p.closeSubpath()
        return p, True
    # stealth: filled concave dart  -Stealth
    p.moveTo(tip); p.lineTo(pt(L, W * 1.15)); p.lineTo(pt(L * 0.55, 0))
    p.lineTo(pt(L, -W * 1.15)); p.closeSubpath()
    return p, True


def arrow_heads(e: Element) -> List[Tuple[QPainterPath, bool]]:
    """Arrowheads (with correct tangents) for lines, Béziers and arcs."""
    start_k, end_k = tip_kinds(e.style.arrows)
    if not start_k and not end_k:
        return []
    lw = e.style.line_width
    heads = []

    def add(kind, tip_xy, out_dir_xy):
        if not kind:
            return
        tip = to_scene(*tip_xy)
        ang = math.atan2(-out_dir_xy[1], out_dir_xy[0])   # cm -> scene
        heads.append(head_path(kind, tip, ang, lw))

    if isinstance(e, LineEl):
        d = (e.x2 - e.x1, e.y2 - e.y1)
        add(end_k, (e.x2, e.y2), d)
        add(start_k, (e.x1, e.y1), (-d[0], -d[1]))
    elif isinstance(e, BezierEl):
        add(end_k, (e.x2, e.y2), (e.x2 - e.c2x, e.y2 - e.c2y))
        add(start_k, (e.x1, e.y1), (e.x1 - e.c1x, e.y1 - e.c1y))
    elif isinstance(e, ArcEl):
        sgn = 1.0 if e.a2 >= e.a1 else -1.0
        for kind, a, s in ((end_k, e.a2, sgn), (start_k, e.a1, -sgn)):
            if not kind:
                continue
            rad = math.radians(a)
            tip = (e.cx + e.r * math.cos(rad), e.cy + e.r * math.sin(rad))
            tangent = (-math.sin(rad) * s, math.cos(rad) * s)
            add(kind, tip, tangent)
    elif isinstance(e, (PlotEl, PolyEl)) and len(getattr(e, "points", [])) >= 2:
        if isinstance(e, PolyEl) and e.closed:
            return heads
        p = e.points
        add(end_k, p[-1], (p[-1][0] - p[-2][0], p[-1][1] - p[-2][1]))
        add(start_k, p[0], (p[0][0] - p[1][0], p[0][1] - p[1][1]))
    return heads


def rounded_radius(st: Style) -> float:
    """px radius if the style carries a 'rounded corners' option."""
    for it in st.extra:
        m = _re.fullmatch(r"rounded corners(?:\s*=\s*([\d.]+)\s*"
                          r"(pt|mm|cm)?)?", it.strip())
        if m:
            if m.group(1):
                v = float(m.group(1))
                cm = v * {"pt": 0.035146, "mm": 0.1,
                          "cm": 1.0}[m.group(2) or "pt"]
                return cm * SCALE
            return 4 * 0.035146 * SCALE      # TikZ default 4pt
    return 0.0


# ----------------------------------------------------------------------
# geometry path for an element (no arrowheads)
# ----------------------------------------------------------------------
def element_path(e: Element, canvas: "Canvas") -> QPainterPath:
    path = QPainterPath()
    if isinstance(e, LineEl):
        path.moveTo(to_scene(e.x1, e.y1)); path.lineTo(to_scene(e.x2, e.y2))
    elif isinstance(e, RectEl):
        r = QRectF(to_scene(e.x1, e.y1), to_scene(e.x2, e.y2)).normalized()
        rad = rounded_radius(e.style)
        if rad > 0:
            path.addRoundedRect(r, rad, rad)
        else:
            path.addRect(r)
    elif isinstance(e, CircleEl):
        path.addEllipse(to_scene(e.cx, e.cy), e.r * SCALE, e.r * SCALE)
    elif isinstance(e, EllipseEl):
        path.addEllipse(to_scene(e.cx, e.cy), e.rx * SCALE, e.ry * SCALE)
    elif isinstance(e, PolyEl) and e.points:
        path.moveTo(to_scene(*e.points[0]))
        for p in e.points[1:]:
            path.lineTo(to_scene(*p))
        if e.closed:
            path.closeSubpath()
    elif isinstance(e, BezierEl):
        path.moveTo(to_scene(e.x1, e.y1))
        path.cubicTo(to_scene(e.c1x, e.c1y), to_scene(e.c2x, e.c2y),
                     to_scene(e.x2, e.y2))
    elif isinstance(e, PlotEl) and e.points:
        path.moveTo(to_scene(*e.points[0]))
        for p in e.points[1:]:
            path.lineTo(to_scene(*p))
    elif isinstance(e, ArcEl):
        rect = QRectF(to_scene(e.cx - e.r, e.cy + e.r),
                      to_scene(e.cx + e.r, e.cy - e.r))
        path.arcMoveTo(rect, e.a1)
        path.arcTo(rect, e.a1, e.a2 - e.a1)
    elif isinstance(e, GridEl):
        x1, x2 = sorted((e.x1, e.x2)); y1, y2 = sorted((e.y1, e.y2))
        s = max(e.step, 0.05)
        x = x1
        while x <= x2 + 1e-9:
            path.moveTo(to_scene(x, y1)); path.lineTo(to_scene(x, y2)); x += s
        y = y1
        while y <= y2 + 1e-9:
            path.moveTo(to_scene(x1, y)); path.lineTo(to_scene(x2, y)); y += s
    return path


ALIGN_FLAGS = {"left": Qt.AlignmentFlag.AlignLeft,
               "right": Qt.AlignmentFlag.AlignRight,
               "center": Qt.AlignmentFlag.AlignHCenter}


def node_box(e: NodeEl):
    """Layout of a node: (display text, font, local QRectF, text flags).

    The rect is in scene px, in a local frame whose origin is the node's
    "at" coordinate (rotation applied separately by the painter).
    """
    disp = latex_to_unicode(e.text).replace("\\\\", "\n")
    pt_size = max(1, round(9 * (e.scale if e.scale > 0 else 1)))
    font = QFont("DejaVu Sans", pt_size)
    font.setItalic("$" in e.text)
    fm = QFontMetricsF(font)
    halign = ALIGN_FLAGS.get(e.align, Qt.AlignmentFlag.AlignHCenter)
    flags = int(halign | Qt.AlignmentFlag.AlignVCenter)
    if e.text_width > 0:
        flags |= int(Qt.TextFlag.TextWordWrap)
        avail = QRectF(0, 0, e.text_width * SCALE * max(e.scale, 0.05), 5000)
    else:
        avail = QRectF(0, 0, 5000, 5000)
    tr = fm.boundingRect(avail, flags, disp)
    sc = max(e.scale, 0.05)
    w = tr.width() + 9
    h = tr.height() + 7
    if e.text_width > 0:
        w = e.text_width * SCALE * sc + 9
    w = max(w, e.min_w * SCALE * sc, 16)
    h = max(h, e.min_h * SCALE * sc, 14)
    if e.shape == "circle":
        w = h = max(w, h)
    # anchor: which point of the box sits on the coordinate
    dx = dy = 0.0
    a = e.anchor
    if "west" in a:
        dx = +w / 2
    if "east" in a:
        dx = -w / 2
    if "north" in a:
        dy = +h / 2       # scene y grows downward
    if "south" in a:
        dy = -h / 2
    rect = QRectF(dx - w / 2, dy - h / 2, w, h)
    return disp, font, rect, flags


def node_transform(e: NodeEl) -> QTransform:
    t = QTransform()
    c = to_scene(e.x, e.y)
    t.translate(c.x(), c.y())
    if abs(e.rotate) > 1e-9:
        t.rotate(-e.rotate)          # TikZ rotates CCW; scene y is flipped
    return t


# ----------------------------------------------------------------------
# coordinate handle
# ----------------------------------------------------------------------
class HandleItem(QGraphicsRectItem):
    SIZE = 8

    def __init__(self, owner: "ElementItem", index: int):
        h = self.SIZE
        super().__init__(-h / 2, -h / 2, h, h, owner)
        self.owner = owner
        self.index = index
        self.setBrush(QBrush(QColor("white")))
        self.setPen(QPen(QColor(30, 120, 255), 1.4))
        self.setZValue(50)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                     True)

    def mousePressEvent(self, ev):
        ev.accept()          # don't let the parent element start moving

    def mouseMoveEvent(self, ev):
        canvas = self.owner.canvas
        x, y = from_scene(ev.scenePos())
        if canvas.snap:
            g = max(canvas.grid_step, 0.01)
            x, y = round(x / g) * g, round(y / g) * g
        x, y = round(x, 3), round(y, 3)
        self.owner.element.move_handle(self.index, x, y)
        self.owner.rebuild()
        self.owner.position_handles()
        canvas.status.emit(f"({x:g}, {y:g})")
        ev.accept()

    def mouseReleaseEvent(self, ev):
        self.owner.canvas.model_changed.emit()
        ev.accept()


def image_display_size(e: ImageEl, canvas: "Canvas"):
    """(w_px, h_px) honouring width/height/keepaspectratio/scale."""
    pm = canvas.image_pixmap(e.path)
    aspect = canvas.image_aspect(e.path)          # h / w
    if e.gscale > 0 and pm:
        w = pm.width() / 72.0 * 2.54 * e.gscale   # natural size at 72 dpi
        h = w * aspect
    elif e.width > 0 and e.height > 0:
        if e.keepaspect:
            w = e.width; h = w * aspect
            if h > e.height + 1e-9:
                h = e.height; w = h / aspect if aspect else w
        else:
            w, h = e.width, e.height
    elif e.width > 0:
        w = e.width; h = w * aspect
    elif e.height > 0:
        h = e.height; w = h / aspect if aspect else h
    else:
        w = 3.0; h = 3.0 * aspect
    return w * SCALE, h * SCALE


def image_transform(e: ImageEl) -> QTransform:
    t = QTransform()
    c = to_scene(e.x, e.y)
    t.translate(c.x(), c.y())
    if abs(e.angle) > 1e-9:
        t.rotate(-e.angle)
    return t


# ----------------------------------------------------------------------
# Graphics item wrapping one Element
# ----------------------------------------------------------------------
class ElementItem(QGraphicsPathItem):
    def __init__(self, element: Element, canvas: "Canvas"):
        super().__init__()
        self.element = element
        self.canvas = canvas
        self._heads: List[Tuple[QPainterPath, bool]] = []
        self._handles: List[HandleItem] = []
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.rebuild()

    # ------------------------------------------------------------------
    def rebuild(self):
        e = self.element
        st = e.style
        pen = QPen(qcolor_alpha(st.draw or "black", st.draw_opacity))
        pen.setWidthF(max(st.line_width * 1.6, 1.0))
        if st.dash == "dashed":
            pen.setStyle(Qt.PenStyle.DashLine)
        elif st.dash == "dotted":
            pen.setStyle(Qt.PenStyle.DotLine)
        self.setPen(pen)
        self.setBrush(QBrush(qcolor_alpha(st.fill, st.fill_opacity))
                      if st.fill else QBrush(Qt.BrushStyle.NoBrush))
        self.setOpacity(st.opacity)
        self.setPath(element_path(e, self.canvas))
        self._heads = arrow_heads(e)

    # -- reshape handles --------------------------------------------------
    def show_handles(self):
        self.hide_handles()
        for i, (hx, hy) in enumerate(self.element.handles()):
            self._handles.append(HandleItem(self, i))
        self.position_handles()

    def hide_handles(self):
        for h in self._handles:
            h.setParentItem(None)
            if h.scene():
                h.scene().removeItem(h)
        self._handles = []

    def position_handles(self):
        for h, (hx, hy) in zip(self._handles, self.element.handles()):
            h.setPos(to_scene(hx, hy))

    # ------------------------------------------------------------------
    def boundingRect(self) -> QRectF:
        e = self.element
        if isinstance(e, NodeEl):
            _, _, rect, _ = node_box(e)
            if e.shape == "circle":
                R = max(rect.width(), rect.height()) / 2 + 3
                rect = QRectF(rect.center().x() - R, rect.center().y() - R,
                              2 * R, 2 * R)
            return node_transform(e).mapRect(rect).adjusted(-3, -3, 3, 3)
        if isinstance(e, ImageEl):
            w, h = image_display_size(e, self.canvas)
            return image_transform(e).mapRect(
                QRectF(-w / 2, -h / 2, w, h)).adjusted(-2, -2, 2, 2)
        if isinstance(e, LibraryEl):
            c = to_scene(e.x, e.y)
            w, h = self.canvas.lib_size_px(e.name)
            return QRectF(c.x() - w / 2, c.y() - h / 2, w, h)
        r = super().boundingRect()
        for hp, _ in self._heads:
            r = r.united(hp.boundingRect())
        return r.adjusted(-12, -12, 12, 12)

    def shape(self):
        if isinstance(self.element, (NodeEl, ImageEl, LibraryEl)):
            p = QPainterPath(); p.addRect(self.boundingRect()); return p
        return super().shape()

    # -- live grid snapping while dragging ---------------------------------
    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
                and self.canvas.snap and isinstance(value, QPointF)):
            g = max(self.canvas.grid_step, 0.01) * SCALE
            value = QPointF(round(value.x() / g) * g,
                            round(value.y() / g) * g)
        return super().itemChange(change, value)

    # ------------------------------------------------------------------
    def paint(self, painter: QPainter, option, widget=None):
        e = self.element
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if isinstance(e, NodeEl):
            painter.setOpacity(e.style.opacity)
            disp, font, rect, flags = node_box(e)
            painter.save()
            painter.setTransform(node_transform(e), True)
            if e.style.fill:
                painter.setBrush(QBrush(qcolor_alpha(e.style.fill,
                                                     e.style.fill_opacity)))
                painter.setPen(Qt.PenStyle.NoPen)
                self._node_shape(painter, e, rect)
            if e.draw_border or e.shape:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(
                    qcolor_alpha(e.style.draw or "black",
                                 e.style.draw_opacity),
                    max(e.style.line_width * 1.6, 1.0)))
                self._node_shape(painter, e, rect)
            painter.setPen(QPen(qcolor(e.style.draw or "black")))
            painter.setFont(font)
            painter.drawText(rect.adjusted(4, 2, -4, -2), flags, disp)
            painter.restore()
        elif isinstance(e, ImageEl):
            pm = self.canvas.image_pixmap(e.path)
            w, h = image_display_size(e, self.canvas)
            r = QRectF(-w / 2, -h / 2, w, h)
            painter.save()
            painter.setTransform(image_transform(e), True)
            if pm:
                painter.drawPixmap(r.toRect(), pm)
            else:
                painter.setPen(QPen(QColor("gray"), 1, Qt.PenStyle.DashLine))
                painter.drawRect(r)
                painter.drawText(r, Qt.AlignmentFlag.AlignCenter,
                                 os.path.basename(e.path) or "image")
            painter.restore()
        elif isinstance(e, LibraryEl):
            pm = self.canvas.lib_pixmap(e.name)
            r = self.boundingRect()
            painter.setOpacity(e.style.opacity)
            if pm:
                painter.drawPixmap(r.toRect(), pm)
            else:
                painter.setPen(QPen(QColor("gray"), 1, Qt.PenStyle.DashLine))
                painter.drawRect(r)
                painter.drawText(r, Qt.AlignmentFlag.AlignCenter, e.name)
        else:
            super().paint(painter, option, widget)
            # distinct arrowheads per tip style
            col = qcolor(e.style.draw or "black")
            for hp, filled in self._heads:
                if filled:
                    painter.fillPath(hp, QBrush(col))
                else:
                    pen = QPen(col, max(e.style.line_width * 1.6, 1.0))
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.strokePath(hp, pen)
            # Bézier control lines while selected
            if self.isSelected() and isinstance(e, BezierEl):
                painter.setPen(QPen(QColor(30, 120, 255, 130), 1,
                                    Qt.PenStyle.DotLine))
                painter.drawLine(to_scene(e.x1, e.y1), to_scene(e.c1x, e.c1y))
                painter.drawLine(to_scene(e.x2, e.y2), to_scene(e.c2x, e.c2y))
        if self.isSelected():
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor(30, 120, 255), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

    @staticmethod
    def _node_shape(painter, e, r):
        if e.shape == "circle":
            R = max(r.width(), r.height()) / 2
            painter.drawEllipse(r.center(), R, R)
        elif e.shape == "ellipse":
            painter.drawEllipse(r)
        elif e.shape == "diamond":
            path = QPainterPath()
            path.moveTo(r.center().x(), r.top() - r.height() * 0.25)
            path.lineTo(r.right() + r.width() * 0.25, r.center().y())
            path.lineTo(r.center().x(), r.bottom() + r.height() * 0.25)
            path.lineTo(r.left() - r.width() * 0.25, r.center().y())
            path.closeSubpath()
            painter.drawPath(path)
        else:
            painter.drawRect(r)

    # move -> update model (ALL moved items, not just the grabbed one) -----
    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        self.canvas.commit_moved_items()

    def mouseDoubleClickEvent(self, ev):
        e = self.element
        if isinstance(e, NodeEl):
            text, ok = QInputDialog.getText(None, "Edit node text",
                                            "LaTeX text:", text=e.text)
            if ok:
                e.text = text
                self.rebuild(); self.update()
                self.canvas.model_changed.emit()
        super().mouseDoubleClickEvent(ev)


# ----------------------------------------------------------------------
# GroupItem — a \begin{scope} rendered with its children, moves as one
# ----------------------------------------------------------------------
class GroupItem(ElementItem):
    def rebuild(self):
        e: GroupEl = self.element
        # remove previous child element items (keep handles machinery empty)
        for ch in list(self.childItems()):
            if isinstance(ch, ElementItem):
                ch.setParentItem(None)
                if ch.scene():
                    ch.scene().removeItem(ch)
        self.setPath(QPainterPath())
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        for child in e.children:
            if isinstance(child, RawEl):
                continue
            it = make_item(child, self.canvas)
            it.setParentItem(self)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            it.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        # shift + scale:  p' = shift + s * p
        t = QTransform()
        t.translate(e.x * SCALE, -e.y * SCALE)
        t.scale(e.s, e.s)
        self.setTransform(t)

    def boundingRect(self) -> QRectF:
        return self.childrenBoundingRect().adjusted(-6, -6, 6, 6)

    def shape(self):
        p = QPainterPath()
        p.addRect(self.boundingRect())
        return p

    def paint(self, painter, option, widget=None):
        if self.isSelected():
            painter.setPen(QPen(QColor(150, 90, 220), 1.2,
                                Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())
            painter.setFont(QFont("DejaVu Sans", 7))
            painter.drawText(self.boundingRect().topLeft()
                             + QPointF(2, -3), "scope")


def make_item(e: Element, canvas: "Canvas") -> ElementItem:
    return GroupItem(e, canvas) if isinstance(e, GroupEl) \
        else ElementItem(e, canvas)


# ----------------------------------------------------------------------
# Canvas
# ----------------------------------------------------------------------
class Canvas(QGraphicsView):
    model_changed = pyqtSignal()          # visual edit -> regenerate code
    selection_changed = pyqtSignal(object)  # Element or None
    status = pyqtSignal(str)
    place_requested = pyqtSignal(float, float)

    def __init__(self):
        super().__init__()
        self._scene = QGraphicsScene(-2000, -2000, 4000, 4000)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.figure: Figure = Figure()
        self.tool = "select"
        self.snap = True
        self.show_grid = True
        self.grid_step = 0.5   # cm — visible grid AND snap step
        self.base_dir = ""     # folder of the opened .tex (relative images)
        self.default_style = Style()
        self.star_points = 5
        self._start: Optional[QPointF] = None
        self._temp: Optional[QGraphicsPathItem] = None
        self._poly_pts = []
        self._free_pts = []
        self._pix_cache = {}
        self._handle_owner: Optional[ElementItem] = None
        self._scene.selectionChanged.connect(self._sel_changed)

    # -- image / library helpers -------------------------------------------
    def resolve_path(self, path: str) -> str:
        if path and not os.path.isabs(path) and self.base_dir:
            return os.path.join(self.base_dir, path)
        return path

    def image_pixmap(self, path) -> Optional[QPixmap]:
        full = self.resolve_path(path)
        if full not in self._pix_cache:
            pm = QPixmap(full)
            self._pix_cache[full] = pm if not pm.isNull() else None
        return self._pix_cache[full]

    def clear_pixmap_cache(self):
        self._pix_cache = {}

    def image_aspect(self, path) -> float:
        pm = self.image_pixmap(path)
        return (pm.height() / pm.width()) if pm and pm.width() else 0.75

    def lib_pixmap(self, name):
        from .library import REGISTRY
        sh = REGISTRY.get(name)
        if sh is None or not sh.thumb:
            return None
        return self.image_pixmap(sh.thumb)

    def lib_size_px(self, name):
        from .library import REGISTRY
        sh = REGISTRY.get(name)
        if sh is None:
            return 40, 40
        return sh.size_cm[0] * SCALE, sh.size_cm[1] * SCALE

    # -- tools / figure -------------------------------------------------------
    def set_tool(self, tool: str):
        self.tool = tool
        self._poly_pts = []
        self._kill_temp()
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag
                         if tool == "select"
                         else QGraphicsView.DragMode.NoDrag)
        hint = ""
        if tool == "polygon":
            hint = "  (click vertices, double-click to close)"
        elif tool == "multiarrow":
            hint = "  (click waypoints, double-click to finish the arrow)"
        self.status.emit(f"Tool: {tool}{hint}")

    def load_figure(self, fig: Figure):
        self.figure = fig
        self.rebuild_scene()

    def rebuild_scene(self):
        self._scene.blockSignals(True)
        self._handle_owner = None
        self._scene.clear()
        self._temp = None
        for el in self.figure.elements:
            if not isinstance(el, RawEl):
                self._scene.addItem(make_item(el, self))
        self._scene.blockSignals(False)
        self.viewport().update()
        self.selection_changed.emit(None)

    def selected_elements(self):
        return [it.element for it in self._scene.selectedItems()
                if isinstance(it, ElementItem)]

    def _sel_changed(self):
        try:
            selected = self._scene.selectedItems()
        except RuntimeError:      # scene already destroyed at shutdown
            return
        items = [it for it in selected if isinstance(it, ElementItem)]
        # reshape handles for exactly one selected element
        if self._handle_owner is not None:
            self._handle_owner.hide_handles()
            self._handle_owner = None
        if len(items) == 1 and items[0].element.handles():
            items[0].show_handles()
            self._handle_owner = items[0]
        self.selection_changed.emit(items[0].element
                                    if len(items) == 1 else None)

    def commit_moved_items(self):
        """Write back every dragged item's offset into the model — a
        multi-selection drag moves several items, but only the grabbed one
        receives the release event."""
        moved = False
        for it in self._scene.items():
            if isinstance(it, ElementItem) and it.parentItem() is None \
                    and not it.pos().isNull():
                dx, dy = it.pos().x() / SCALE, -it.pos().y() / SCALE
                it.element.translate(round(dx, 3), round(dy, 3))
                it.setPos(0, 0)
                it.rebuild()
                it.position_handles()
                moved = True
        if moved:
            self.model_changed.emit()

    def delete_selected(self):
        for el in self.selected_elements():
            if el in self.figure.elements:
                self.figure.elements.remove(el)
        self.rebuild_scene()
        self.model_changed.emit()

    def refresh_selected(self):
        for it in self._scene.selectedItems():
            if isinstance(it, ElementItem):
                it.rebuild(); it.position_handles(); it.update()

    # -- background grid ----------------------------------------------------
    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, QColor("#fcfcf8"))
        if not self.show_grid:
            return
        step = max(self.grid_step, 0.05) * SCALE
        pen_minor = QPen(QColor(228, 228, 220))
        pen_major = QPen(QColor(205, 205, 195))
        x = math.floor(rect.left() / step) * step
        while x < rect.right():
            painter.setPen(pen_major if abs(x % SCALE) < 1e-6 else pen_minor)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
        y = math.floor(rect.top() / step) * step
        while y < rect.bottom():
            painter.setPen(pen_major if abs(y % SCALE) < 1e-6 else pen_minor)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step
        painter.setPen(QPen(QColor(160, 160, 210), 1.4))
        painter.drawLine(QPointF(rect.left(), 0), QPointF(rect.right(), 0))
        painter.drawLine(QPointF(0, rect.top()), QPointF(0, rect.bottom()))

    # -- zoom ---------------------------------------------------------------
    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            f = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
            self.scale(f, f)
        else:
            super().wheelEvent(ev)

    # -- mouse / drawing ------------------------------------------------------
    def _snap_pt(self, sp: QPointF) -> QPointF:
        x, y = from_scene(sp)
        if self.snap:
            g = max(self.grid_step, 0.01)
            x, y = round(x / g) * g, round(y / g) * g
        return to_scene(x, y)

    def mousePressEvent(self, ev):
        if self.tool == "select" or ev.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(ev)
        sp = self._snap_pt(self.mapToScene(ev.pos()))
        x, y = from_scene(sp)

        if self.tool == "place":
            self.place_requested.emit(x, y)
            return
        if self.tool == "node":
            text, ok = QInputDialog.getText(self, "Node text", "LaTeX text:",
                                            text="text")
            if ok:
                self._add(NodeEl(style=self.default_style.copy(), x=x, y=y,
                                 text=text or "text"))
            return
        if self.tool == "image":
            path, _ = QFileDialog.getOpenFileName(
                self, "Insert image", self.base_dir or "",
                "Images (*.png *.jpg *.jpeg *.pdf *.eps)")
            if path:
                self._add(ImageEl(x=x, y=y, path=self._relativize(path),
                                  width=3.0))
            return
        if self.tool in ("polygon", "multiarrow"):
            self._poly_pts.append((x, y))
            self._preview_poly()
            return
        if self.tool == "freehand":
            self._free_pts = [(x, y)]
        self._start = sp

    def _relativize(self, path: str) -> str:
        """Use a path relative to the figure's folder when possible."""
        if self.base_dir:
            rel = os.path.relpath(path, self.base_dir)
            if not rel.startswith(".."):
                return rel
        return path

    def mouseMoveEvent(self, ev):
        if self.tool == "select" or self._start is None:
            if self.tool in ("polygon", "multiarrow") and self._poly_pts:
                self._preview_poly(self.mapToScene(ev.pos()))
            return super().mouseMoveEvent(ev)
        cur = self._snap_pt(self.mapToScene(ev.pos()))
        if self.tool == "freehand":
            x, y = from_scene(self.mapToScene(ev.pos()))
            if (not self._free_pts
                    or (x - self._free_pts[-1][0]) ** 2
                    + (y - self._free_pts[-1][1]) ** 2 > 0.01):
                self._free_pts.append((round(x, 2), round(y, 2)))
        self._preview_drag(self._start, cur)

    def mouseReleaseEvent(self, ev):
        if self.tool == "select":
            return super().mouseReleaseEvent(ev)
        if self._start is None or self.tool in ("polygon", "multiarrow"):
            return super().mouseReleaseEvent(ev)
        end = self._snap_pt(self.mapToScene(ev.pos()))
        x1, y1 = from_scene(self._start); x2, y2 = from_scene(end)
        self._start = None
        self._kill_temp()
        st = self.default_style.copy()
        tiny = abs(x2 - x1) < 0.05 and abs(y2 - y1) < 0.05

        if self.tool == "freehand":
            if len(self._free_pts) > 2:
                self._add(PlotEl(style=st, points=self._free_pts[::2]
                                 or self._free_pts))
            self._free_pts = []
            return
        if tiny:
            return
        if self.tool == "line":
            self._add(LineEl(style=st, x1=x1, y1=y1, x2=x2, y2=y2))
        elif self.tool == "arrow":
            st.arrows = st.arrows or "->"
            self._add(LineEl(style=st, x1=x1, y1=y1, x2=x2, y2=y2))
        elif self.tool == "rect":
            self._add(RectEl(style=st, x1=x1, y1=y1, x2=x2, y2=y2))
        elif self.tool == "circle":
            r = math.hypot(x2 - x1, y2 - y1)
            self._add(CircleEl(style=st, cx=x1, cy=y1, r=round(r, 3)))
        elif self.tool == "ellipse":
            self._add(EllipseEl(style=st, cx=(x1 + x2) / 2, cy=(y1 + y2) / 2,
                                rx=abs(x2 - x1) / 2 or 0.1,
                                ry=abs(y2 - y1) / 2 or 0.1))
        elif self.tool == "arc":
            r = math.hypot(x2 - x1, y2 - y1)
            a1 = math.degrees(math.atan2(y2 - y1, x2 - x1))
            self._add(ArcEl(style=st, cx=x1, cy=y1, r=round(r, 3),
                            a1=round(a1), a2=round(a1) + 90))
        elif self.tool == "grid":
            st.draw = st.draw if st.draw != "black" else "gray!60"
            self._add(GridEl(style=st, x1=x1, y1=y1, x2=x2, y2=y2, step=0.5))
        elif self.tool == "star":
            self._add(self._make_star(x1, y1,
                                      math.hypot(x2 - x1, y2 - y1), st))
        elif self.tool == "bezier":
            self._add(self._line_to_bezier(
                LineEl(style=st, x1=x1, y1=y1, x2=x2, y2=y2)))

    def mouseDoubleClickEvent(self, ev):
        if self.tool == "polygon" and len(self._poly_pts) >= 3:
            self._kill_temp()
            self._add(PolyEl(style=self.default_style.copy(),
                             points=self._poly_pts[:], closed=True))
            self._poly_pts = []
            return
        if self.tool == "multiarrow" and len(self._poly_pts) >= 2:
            self._kill_temp()
            st = self.default_style.copy()
            st.arrows = st.arrows or "->"
            self._add(PolyEl(style=st, points=self._poly_pts[:],
                             closed=False))
            self._poly_pts = []
            return
        super().mouseDoubleClickEvent(ev)

    # -- arrow keys: precise nudging -----------------------------------------
    def keyPressEvent(self, ev):
        key = ev.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            return
        if key == Qt.Key.Key_Escape:
            self._poly_pts = []
            self._kill_temp()
            return
        deltas = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                  Qt.Key.Key_Up: (0, 1), Qt.Key.Key_Down: (0, -1)}
        if key in deltas and self.selected_elements():
            mods = ev.modifiers()
            if mods & Qt.KeyboardModifier.ControlModifier:
                step = 0.01                    # ultra-fine
            elif mods & Qt.KeyboardModifier.ShiftModifier:
                step = self.grid_step          # one grid cell
            else:
                step = 0.05                    # fine (default)
            dx, dy = deltas[key]
            for it in self._scene.selectedItems():
                if isinstance(it, ElementItem):
                    it.element.translate(round(dx * step, 3),
                                         round(dy * step, 3))
                    it.rebuild(); it.position_handles(); it.update()
            self.status.emit(f"Nudged by {step:g} cm "
                             "(plain=0.05, Shift=grid, Ctrl=0.01)")
            self.model_changed.emit()
            return
        super().keyPressEvent(ev)

    # -- previews ---------------------------------------------------------
    def _preview_drag(self, a: QPointF, b: QPointF):
        p = QPainterPath()
        if self.tool in ("line", "arrow", "bezier"):
            p.moveTo(a); p.lineTo(b)
        elif self.tool in ("rect", "grid"):
            p.addRect(QRectF(a, b).normalized())
        elif self.tool in ("circle", "arc", "star"):
            r = math.hypot(b.x() - a.x(), b.y() - a.y())
            p.addEllipse(a, r, r)
        elif self.tool == "ellipse":
            p.addEllipse(QRectF(a, b).normalized())
        elif self.tool == "freehand" and len(self._free_pts) > 1:
            p.moveTo(to_scene(*self._free_pts[0]))
            for q in self._free_pts[1:]:
                p.lineTo(to_scene(*q))
        self._set_temp(p)

    def _preview_poly(self, cursor: Optional[QPointF] = None):
        p = QPainterPath()
        if self._poly_pts:
            p.moveTo(to_scene(*self._poly_pts[0]))
            for q in self._poly_pts[1:]:
                p.lineTo(to_scene(*q))
            if cursor is not None:
                p.lineTo(cursor)
        self._set_temp(p)

    def _set_temp(self, path: QPainterPath):
        if self._temp is None:
            self._temp = self._scene.addPath(
                path, QPen(QColor(30, 120, 255), 1, Qt.PenStyle.DashLine))
        else:
            self._temp.setPath(path)

    def _kill_temp(self):
        if self._temp is not None:
            try:
                self._scene.removeItem(self._temp)
            except RuntimeError:
                pass
            self._temp = None

    # -- element creation -------------------------------------------------
    def _add(self, el: Element):
        self.figure.elements.append(el)
        self.rebuild_scene()
        self.model_changed.emit()

    def _make_star(self, cx, cy, r, st: Style) -> PolyEl:
        n = self.star_points
        pts = []
        for i in range(2 * n):
            rad = r if i % 2 == 0 else r * 0.45
            ang = math.pi / 2 + i * math.pi / n
            pts.append((round(cx + rad * math.cos(ang), 3),
                        round(cy + rad * math.sin(ang), 3)))
        return PolyEl(style=st, points=pts, closed=True)

    @staticmethod
    def _line_to_bezier(l: LineEl) -> BezierEl:
        dx, dy = l.x2 - l.x1, l.y2 - l.y1
        nx, ny = -dy * 0.35, dx * 0.35     # perpendicular offset
        return BezierEl(style=l.style,
                        x1=l.x1, y1=l.y1,
                        c1x=round(l.x1 + dx / 3 + nx, 3),
                        c1y=round(l.y1 + dy / 3 + ny, 3),
                        c2x=round(l.x1 + 2 * dx / 3 + nx, 3),
                        c2y=round(l.y1 + 2 * dy / 3 + ny, 3),
                        x2=l.x2, y2=l.y2)
