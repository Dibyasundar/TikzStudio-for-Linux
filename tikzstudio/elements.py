"""Data model for TikZ Studio.

Every drawable is an Element that can serialize itself to a TikZ command
(`to_tikz`).  The parser (parser.py) does the reverse, so the code editor
and the canvas stay in two-way sync.  Anything the parser cannot
understand is preserved verbatim as a RawElement, so hand-written TikZ is
never destroyed.
"""

from dataclasses import dataclass, field
from typing import List, Tuple
import math

SCALE = 40.0  # pixels per TikZ cm on the canvas


def fnum(v: float) -> str:
    """Format a number for TikZ output (max 3 decimals, no trailing zeros)."""
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


# ----------------------------------------------------------------------
# Style
# ----------------------------------------------------------------------
@dataclass
class Style:
    draw: str = "black"        # TikZ colour expression, "" = no stroke
    fill: str = ""             # "" = no fill
    line_width: float = 0.4    # pt
    dash: str = "solid"        # solid | dashed | dotted
    arrows: str = ""           # "" | -> | <- | <->
    opacity: float = 1.0
    fill_opacity: float = 1.0
    draw_opacity: float = 1.0
    extra: List[str] = field(default_factory=list)  # preserved verbatim

    def options(self, extra: List[str] = None) -> str:
        o: List[str] = []
        if self.arrows:
            o.append(self.arrows)
        if self.draw and self.draw != "black":
            o.append(f"color={self.draw}")
        if self.fill:
            o.append(f"fill={self.fill}")
        if abs(self.line_width - 0.4) > 1e-9:
            o.append(f"line width={fnum(self.line_width)}pt")
        if self.dash in ("dashed", "dotted"):
            o.append(self.dash)
        if self.opacity < 0.999:
            o.append(f"opacity={fnum(self.opacity)}")
        if self.fill_opacity < 0.999:
            o.append(f"fill opacity={fnum(self.fill_opacity)}")
        if self.draw_opacity < 0.999:
            o.append(f"draw opacity={fnum(self.draw_opacity)}")
        if extra:
            o.extend(extra)
        if self.extra:
            o.extend(self.extra)
        return f"[{', '.join(o)}]" if o else ""

    def copy(self) -> "Style":
        return Style(self.draw, self.fill, self.line_width,
                     self.dash, self.arrows, self.opacity,
                     self.fill_opacity, self.draw_opacity,
                     list(self.extra))


# ----------------------------------------------------------------------
# Elements
# ----------------------------------------------------------------------
@dataclass
class Element:
    style: Style = field(default_factory=Style)

    def to_tikz(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def translate(self, dx: float, dy: float):
        pass

    def handles(self):
        """Draggable coordinate handles: list of (x, y) in cm."""
        return []

    def move_handle(self, i: int, x: float, y: float):
        pass

    def bake(self, s: float, dx: float, dy: float) -> bool:
        """Apply scale-about-origin then shift to the coordinates
        (used when ungrouping a scope).  Returns False if impossible."""
        return False


@dataclass
class LineEl(Element):
    x1: float = 0; y1: float = 0; x2: float = 1; y2: float = 0

    def to_tikz(self):
        return (f"\\draw{self.style.options()} ({fnum(self.x1)},{fnum(self.y1)})"
                f" -- ({fnum(self.x2)},{fnum(self.y2)});")

    def translate(self, dx, dy):
        self.x1 += dx; self.y1 += dy; self.x2 += dx; self.y2 += dy

    def handles(self):
        return [(self.x1, self.y1), (self.x2, self.y2)]

    def move_handle(self, i, x, y):
        if i == 0:
            self.x1, self.y1 = x, y
        else:
            self.x2, self.y2 = x, y

    def bake(self, s, dx, dy):
        self.x1 = dx + s * self.x1; self.y1 = dy + s * self.y1
        self.x2 = dx + s * self.x2; self.y2 = dy + s * self.y2
        return True


@dataclass
class RectEl(Element):
    x1: float = 0; y1: float = 0; x2: float = 1; y2: float = 1

    def to_tikz(self):
        return (f"\\draw{self.style.options()} ({fnum(self.x1)},{fnum(self.y1)})"
                f" rectangle ({fnum(self.x2)},{fnum(self.y2)});")

    def translate(self, dx, dy):
        self.x1 += dx; self.y1 += dy; self.x2 += dx; self.y2 += dy

    def handles(self):
        return [(self.x1, self.y1), (self.x2, self.y2),
                (self.x1, self.y2), (self.x2, self.y1)]

    def move_handle(self, i, x, y):
        if i == 0:
            self.x1, self.y1 = x, y
        elif i == 1:
            self.x2, self.y2 = x, y
        elif i == 2:
            self.x1, self.y2 = x, y
        else:
            self.x2, self.y1 = x, y

    def bake(self, s, dx, dy):
        self.x1 = dx + s * self.x1; self.y1 = dy + s * self.y1
        self.x2 = dx + s * self.x2; self.y2 = dy + s * self.y2
        return True


@dataclass
class CircleEl(Element):
    cx: float = 0; cy: float = 0; r: float = 1

    def to_tikz(self):
        return (f"\\draw{self.style.options()} ({fnum(self.cx)},{fnum(self.cy)})"
                f" circle ({fnum(self.r)});")

    def translate(self, dx, dy):
        self.cx += dx; self.cy += dy

    def handles(self):
        return [(self.cx, self.cy), (self.cx + self.r, self.cy)]

    def move_handle(self, i, x, y):
        if i == 0:
            self.cx, self.cy = x, y
        else:
            self.r = round(max(math.hypot(x - self.cx, y - self.cy), 0.05), 3)

    def bake(self, s, dx, dy):
        self.cx = dx + s * self.cx; self.cy = dy + s * self.cy
        self.r *= s
        return True


@dataclass
class EllipseEl(Element):
    cx: float = 0; cy: float = 0; rx: float = 1; ry: float = 0.5

    def to_tikz(self):
        return (f"\\draw{self.style.options()} ({fnum(self.cx)},{fnum(self.cy)})"
                f" ellipse ({fnum(self.rx)} and {fnum(self.ry)});")

    def translate(self, dx, dy):
        self.cx += dx; self.cy += dy

    def handles(self):
        return [(self.cx, self.cy), (self.cx + self.rx, self.cy),
                (self.cx, self.cy + self.ry)]

    def move_handle(self, i, x, y):
        if i == 0:
            self.cx, self.cy = x, y
        elif i == 1:
            self.rx = round(max(abs(x - self.cx), 0.05), 3)
        else:
            self.ry = round(max(abs(y - self.cy), 0.05), 3)

    def bake(self, s, dx, dy):
        self.cx = dx + s * self.cx; self.cy = dy + s * self.cy
        self.rx *= s; self.ry *= s
        return True


@dataclass
class PolyEl(Element):
    """Closed or open poly-line.  Also used for stars and callouts."""
    points: List[Tuple[float, float]] = field(default_factory=list)
    closed: bool = True

    def to_tikz(self):
        pts = " -- ".join(f"({fnum(x)},{fnum(y)})" for x, y in self.points)
        tail = " -- cycle;" if self.closed else ";"
        return f"\\draw{self.style.options()} {pts}{tail}"

    def translate(self, dx, dy):
        self.points = [(x + dx, y + dy) for x, y in self.points]

    def handles(self):
        return list(self.points)

    def move_handle(self, i, x, y):
        self.points[i] = (x, y)

    def bake(self, s, dx, dy):
        self.points = [(dx + s * x, dy + s * y) for x, y in self.points]
        return True


@dataclass
class BezierEl(Element):
    x1: float = 0; y1: float = 0
    c1x: float = 0; c1y: float = 0
    c2x: float = 0; c2y: float = 0
    x2: float = 1; y2: float = 0

    def to_tikz(self):
        return (f"\\draw{self.style.options()} ({fnum(self.x1)},{fnum(self.y1)})"
                f" .. controls ({fnum(self.c1x)},{fnum(self.c1y)}) and"
                f" ({fnum(self.c2x)},{fnum(self.c2y)}) .."
                f" ({fnum(self.x2)},{fnum(self.y2)});")

    def translate(self, dx, dy):
        for a in ("x1", "c1x", "c2x", "x2"):
            setattr(self, a, getattr(self, a) + dx)
        for a in ("y1", "c1y", "c2y", "y2"):
            setattr(self, a, getattr(self, a) + dy)

    def handles(self):
        return [(self.x1, self.y1), (self.c1x, self.c1y),
                (self.c2x, self.c2y), (self.x2, self.y2)]

    def move_handle(self, i, x, y):
        a = (("x1", "y1"), ("c1x", "c1y"), ("c2x", "c2y"), ("x2", "y2"))[i]
        setattr(self, a[0], x); setattr(self, a[1], y)

    def bake(self, s, dx, dy):
        for ax, ay in (("x1", "y1"), ("c1x", "c1y"),
                       ("c2x", "c2y"), ("x2", "y2")):
            setattr(self, ax, dx + s * getattr(self, ax))
            setattr(self, ay, dy + s * getattr(self, ay))
        return True


@dataclass
class PlotEl(Element):
    """Smooth freehand curve using \\draw plot[smooth] coordinates."""
    points: List[Tuple[float, float]] = field(default_factory=list)

    def to_tikz(self):
        pts = " ".join(f"({fnum(x)},{fnum(y)})" for x, y in self.points)
        return f"\\draw{self.style.options()} plot[smooth] coordinates {{{pts}}};"

    def translate(self, dx, dy):
        self.points = [(x + dx, y + dy) for x, y in self.points]

    def handles(self):
        return list(self.points)

    def move_handle(self, i, x, y):
        self.points[i] = (x, y)

    def bake(self, s, dx, dy):
        self.points = [(dx + s * x, dy + s * y) for x, y in self.points]
        return True


@dataclass
class ArcEl(Element):
    cx: float = 0; cy: float = 0; r: float = 1
    a1: float = 0; a2: float = 90

    def to_tikz(self):
        sx = self.cx + self.r * math.cos(math.radians(self.a1))
        sy = self.cy + self.r * math.sin(math.radians(self.a1))
        return (f"\\draw{self.style.options()} ({fnum(sx)},{fnum(sy)})"
                f" arc ({fnum(self.a1)}:{fnum(self.a2)}:{fnum(self.r)});")

    def translate(self, dx, dy):
        self.cx += dx; self.cy += dy

    def handles(self):
        p1 = (self.cx + self.r * math.cos(math.radians(self.a1)),
              self.cy + self.r * math.sin(math.radians(self.a1)))
        p2 = (self.cx + self.r * math.cos(math.radians(self.a2)),
              self.cy + self.r * math.sin(math.radians(self.a2)))
        return [(self.cx, self.cy), p1, p2]

    def move_handle(self, i, x, y):
        if i == 0:
            self.cx, self.cy = x, y
        elif i == 1:
            self.r = round(max(math.hypot(x - self.cx, y - self.cy), 0.05), 3)
            self.a1 = round(math.degrees(math.atan2(y - self.cy, x - self.cx)), 1)
        else:
            self.a2 = round(math.degrees(math.atan2(y - self.cy, x - self.cx)), 1)

    def bake(self, s, dx, dy):
        self.cx = dx + s * self.cx; self.cy = dy + s * self.cy
        self.r *= s
        return True


@dataclass
class GridEl(Element):
    x1: float = 0; y1: float = 0; x2: float = 4; y2: float = 4
    step: float = 0.5

    def to_tikz(self):
        return (f"\\draw{self.style.options([f'step={fnum(self.step)}'])}"
                f" ({fnum(self.x1)},{fnum(self.y1)}) grid"
                f" ({fnum(self.x2)},{fnum(self.y2)});")

    def translate(self, dx, dy):
        self.x1 += dx; self.y1 += dy; self.x2 += dx; self.y2 += dy

    def handles(self):
        return [(self.x1, self.y1), (self.x2, self.y2)]

    def move_handle(self, i, x, y):
        if i == 0:
            self.x1, self.y1 = x, y
        else:
            self.x2, self.y2 = x, y

    def bake(self, s, dx, dy):
        self.x1 = dx + s * self.x1; self.y1 = dy + s * self.y1
        self.x2 = dx + s * self.x2; self.y2 = dy + s * self.y2
        self.step *= s
        return True


@dataclass
class NodeEl(Element):
    x: float = 0; y: float = 0
    text: str = "text"
    shape: str = ""          # "", rectangle, circle, ellipse, star, ...
    draw_border: bool = False
    anchor: str = ""         # west, north east, ...
    scale: float = 1.0
    rotate: float = 0.0
    min_w: float = 0.0       # minimum width  (cm)
    min_h: float = 0.0       # minimum height (cm)
    text_width: float = 0.0  # cm (enables wrapping)
    align: str = ""          # left | center | right

    def to_tikz(self):
        extra = []
        if self.shape:
            extra.append(self.shape)
        if self.draw_border or self.shape:
            extra.append("draw")
        if self.anchor:
            extra.append(f"anchor={self.anchor}")
        if abs(self.rotate) > 1e-9:
            extra.append(f"rotate={fnum(self.rotate)}")
        if abs(self.scale - 1) > 1e-9:
            extra.append(f"scale={fnum(self.scale)}")
        if self.min_w > 0:
            extra.append(f"minimum width={fnum(self.min_w)}cm")
        if self.min_h > 0:
            extra.append(f"minimum height={fnum(self.min_h)}cm")
        if self.text_width > 0:
            extra.append(f"text width={fnum(self.text_width)}cm")
        if self.align:
            extra.append(f"align={self.align}")
        opts = self.style.options(extra) \
            if (extra or self.style.options()) else ""
        return f"\\node{opts} at ({fnum(self.x)},{fnum(self.y)}) {{{self.text}}};"

    def translate(self, dx, dy):
        self.x += dx; self.y += dy

    def bake(self, s, dx, dy):
        self.x = dx + s * self.x; self.y = dy + s * self.y
        return True


@dataclass
class ImageEl(Element):
    x: float = 0; y: float = 0
    path: str = ""
    width: float = 3.0      # cm; 0 = unset
    height: float = 0.0     # cm; 0 = unset
    gscale: float = 0.0     # graphicx scale=; 0 = unset
    angle: float = 0.0      # graphicx angle= (degrees, CCW)
    keepaspect: bool = False
    gextra: List[str] = field(default_factory=list)  # other graphicx opts
    node_opts: str = ""     # options of the wrapping \\node, verbatim

    def to_tikz(self):
        g = []
        if self.width > 0:
            g.append(f"width={fnum(self.width)}cm")
        if self.height > 0:
            g.append(f"height={fnum(self.height)}cm")
        if self.keepaspect:
            g.append("keepaspectratio")
        if self.gscale > 0:
            g.append(f"scale={fnum(self.gscale)}")
        if abs(self.angle) > 1e-9:
            g.append(f"angle={fnum(self.angle)}")
        g.extend(self.gextra)
        gopt = f"[{', '.join(g)}]" if g else ""
        nopt = f"[{self.node_opts}]" if self.node_opts else ""
        return (f"\\node{nopt} at ({fnum(self.x)},{fnum(self.y)})"
                f" {{\\includegraphics{gopt}{{{self.path}}}}};")

    def translate(self, dx, dy):
        self.x += dx; self.y += dy

    def bake(self, s, dx, dy):
        self.x = dx + s * self.x; self.y = dy + s * self.y
        self.width *= s
        return True


@dataclass
class LibraryEl(Element):
    """An element placed from the pre-compiled library palette."""
    name: str = ""
    template: str = ""     # contains @X@ / @Y@ anchor placeholders
    x: float = 0; y: float = 0

    def to_tikz(self):
        return (self.template.replace("@X@", fnum(self.x))
                .replace("@Y@", fnum(self.y)) + f" % lib:{self.name}")

    def translate(self, dx, dy):
        self.x += dx; self.y += dy

    def bake(self, s, dx, dy):
        self.x = dx + s * self.x; self.y = dy + s * self.y
        return True     # note: internal size of the snippet is not scaled


@dataclass
class GroupEl(Element):
    """A \\begin{scope} grouping several elements; can be moved (shift)
    and scaled (scale) as one.  TikZ applies the options in order, so
    with [shift, scale] a child point p maps to  shift + scale * p."""
    children: List[Element] = field(default_factory=list)
    x: float = 0; y: float = 0; s: float = 1.0

    def to_tikz(self):
        opts = []
        if abs(self.x) > 1e-9 or abs(self.y) > 1e-9:
            opts.append(f"shift={{({fnum(self.x)},{fnum(self.y)})}}")
        if abs(self.s - 1) > 1e-9:
            opts.append(f"scale={fnum(self.s)}")
        head = "\\begin{scope}" + (f"[{', '.join(opts)}]" if opts else "")
        inner = "\n".join("  " + c.to_tikz().replace("\n", "\n  ")
                          for c in self.children)
        return f"{head}\n{inner}\n\\end{{scope}}"

    def translate(self, dx, dy):
        self.x += dx; self.y += dy

    def bake(self, s, dx, dy):
        # compose: outer(inner(p)) = (dx,dy) + s*( (x,y) + self.s*p )
        self.x = dx + s * self.x; self.y = dy + s * self.y
        self.s *= s
        return True


@dataclass
class RawEl(Element):
    """Any TikZ code the parser does not understand — preserved verbatim."""
    code: str = ""

    def to_tikz(self):
        return self.code


# ----------------------------------------------------------------------
# Figure & Document
# ----------------------------------------------------------------------
class Figure:
    def __init__(self, name="figure1"):
        self.name = name
        self.elements: List[Element] = []
        self.env_options: str = ""      # options of \begin{tikzpicture}[...]

    def body_code(self) -> str:
        return "\n".join(e.to_tikz() for e in self.elements)

    def full_code(self) -> str:
        opt = f"[{self.env_options}]" if self.env_options else ""
        body = self.body_code()
        body = ("  " + body.replace("\n", "\n  ")) if body else "  % empty"
        return f"\\begin{{tikzpicture}}{opt}\n{body}\n\\end{{tikzpicture}}"


class TikzDocument:
    """A standalone LaTeX document holding one or more TikZ figures."""

    def __init__(self):
        self.figures: List[Figure] = [Figure()]
        self.doc_class_options = "tikz,border=2mm"
        self.packages: List[str] = []                 # e.g. "amsmath", "graphicx"
        self.tikz_libraries: List[str] = ["arrows.meta"]
        self.extra_preamble: str = ""

    # -- preamble -------------------------------------------------------
    def preamble(self) -> str:
        lines = [f"\\documentclass[{self.doc_class_options}]{{standalone}}"]
        for p in self.packages:
            if p.strip():
                lines.append(f"\\usepackage{{{p.strip()}}}")
        if self.tikz_libraries:
            libs = ",".join(l.strip() for l in self.tikz_libraries if l.strip())
            if libs:
                lines.append(f"\\usetikzlibrary{{{libs}}}")
        if self.extra_preamble.strip():
            lines.append(self.extra_preamble.strip())
        return "\n".join(lines)

    def full_document(self) -> str:
        figs = "\n\n".join(f.full_code() for f in self.figures)
        return (f"{self.preamble()}\n\n\\begin{{document}}\n"
                f"{figs}\n\\end{{document}}\n")


# ----------------------------------------------------------------------
# Templates inserted from the Insert menu
# ----------------------------------------------------------------------
TREE_TEMPLATE = r"""\node {root}
  child {node {left}
    child {node {A}}
    child {node {B}}}
  child {node {right}
    child {node {C}}};"""

CALLOUT_TEMPLATE = (r"\node[ellipse callout, draw, fill=yellow!20, "
                    r"callout absolute pointer={(2,-1)}] at (0,1) {Hello!};")
