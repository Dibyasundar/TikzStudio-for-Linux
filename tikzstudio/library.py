"""Pre-compiled TikZ element library.

On first run, every element in the built-in catalog is compiled once with
pdflatex (all in a single multi-page standalone document) and rendered to
transparent PNG thumbnails with pdftocairo.  The thumbnails live in
~/.cache/tikzstudio/library and are shown in the WYSIWYG palette; placing
one inserts its TikZ snippet with the click position substituted.

Users can add their own elements: the snippet is test-compiled, a
thumbnail rendered, and it appears in the palette permanently.

Each element is a *single TikZ statement* (a \\node, a \\draw, or a
\\begin{scope}...\\end{scope} block) whose template contains the anchor
placeholders @X@ and @Y@.  Generated code carries a trailing
"% lib:<name>" marker so the parser can rebuild the element from code
(two-way sync); if the user edits the statement so it no longer matches
its template, it simply degrades to raw TikZ and still compiles.
"""

import json
import os
import re
import shutil
import subprocess

from PyQt6.QtCore import QObject, pyqtSignal

NUM = r"[-+]?\d*\.?\d+"
CACHE_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "tikzstudio")
LIB_DIR = os.path.join(CACHE_DIR, "library")
THUMB_DPI = 110
PX_PER_CM = THUMB_DPI / 2.54


# ----------------------------------------------------------------------
# Built-in catalog: (name, [tikz libraries], template)
# ----------------------------------------------------------------------
def _node(shape, extra="", size="minimum size=9mm"):
    e = f", {extra}" if extra else ""
    return (f"\\node[{shape}, draw{e}, {size}] "
            f"at (@X@,@Y@) {{}};")


CATALOG = [
    # -- geometric node shapes -------------------------------------------
    ("diamond",            ["shapes.geometric"], _node("diamond")),
    ("trapezium",          ["shapes.geometric"], _node("trapezium")),
    ("semicircle",         ["shapes.geometric"], _node("semicircle")),
    ("triangle",           ["shapes.geometric"], _node("isosceles triangle")),
    ("kite",               ["shapes.geometric"], _node("kite")),
    ("dart",               ["shapes.geometric"], _node("dart")),
    ("circular sector",    ["shapes.geometric"], _node("circular sector")),
    ("cylinder",           ["shapes.geometric"], _node("cylinder", "shape aspect=0.6")),
    ("pentagon",           ["shapes.geometric"], _node("regular polygon", "regular polygon sides=5")),
    ("hexagon",            ["shapes.geometric"], _node("regular polygon", "regular polygon sides=6")),
    ("star node",          ["shapes.geometric"], _node("star", "star points=5")),
    # -- symbols ------------------------------------------------------------
    ("cloud",              ["shapes.symbols"],   _node("cloud", "aspect=2")),
    ("starburst",          ["shapes.symbols"],   _node("starburst")),
    ("signal",             ["shapes.symbols"],   _node("signal")),
    ("tape",               ["shapes.symbols"],   _node("tape")),
    ("forbidden sign",     ["shapes.symbols"],   _node("forbidden sign", "line width=1pt")),
    ("magnifying glass",   ["shapes.symbols"],   _node("magnifying glass", "line width=1.5pt", "minimum size=6mm")),
    # -- misc -----------------------------------------------------------------
    ("rounded rectangle",  ["shapes.misc"],      _node("rounded rectangle")),
    ("chamfered rectangle",["shapes.misc"],      _node("chamfered rectangle")),
    ("cross out",          ["shapes.misc"],      _node("cross out")),
    # -- callouts ----------------------------------------------------------
    ("rectangle callout",  ["shapes.callouts"],  _node("rectangle callout")),
    ("ellipse callout",    ["shapes.callouts"],  _node("ellipse callout")),
    ("cloud callout",      ["shapes.callouts"],  _node("cloud callout", "aspect=2", "minimum size=7mm")),
    # -- arrows ------------------------------------------------------------
    ("single arrow",       ["shapes.arrows"],    _node("single arrow")),
    ("double arrow",       ["shapes.arrows"],    _node("double arrow")),
    ("arrow box",          ["shapes.arrows"],    _node("arrow box", "", "minimum size=6mm")),
    # -- decorated paths ------------------------------------------------------
    ("snake path",  ["decorations.pathmorphing"],
     "\\draw[decorate, decoration=snake, shift={(@X@,@Y@)}] (-0.9,0) -- (0.9,0);"),
    ("zigzag path", ["decorations.pathmorphing"],
     "\\draw[decorate, decoration=zigzag, shift={(@X@,@Y@)}] (-0.9,0) -- (0.9,0);"),
    ("coil path",   ["decorations.pathmorphing"],
     "\\draw[decorate, decoration={coil, aspect=0.6}, shift={(@X@,@Y@)}] (-0.9,0) -- (0.9,0);"),
    ("brace",       ["decorations.pathreplacing"],
     "\\draw[decorate, decoration={brace, amplitude=6pt}, shift={(@X@,@Y@)}] (-0.9,0) -- (0.9,0);"),
    # -- flowchart blocks ------------------------------------------------------
    ("flow: process",  [],
     "\\node[rectangle, draw, fill=blue!15, minimum width=16mm, minimum height=8mm] at (@X@,@Y@) {};"),
    ("flow: decision", ["shapes.geometric"],
     "\\node[diamond, draw, fill=orange!25, aspect=1.6, minimum width=14mm] at (@X@,@Y@) {};"),
    ("flow: terminator", ["shapes.misc"],
     "\\node[rounded rectangle, draw, fill=green!20, minimum width=16mm, minimum height=8mm] at (@X@,@Y@) {};"),
    ("flow: data", ["shapes.geometric"],
     "\\node[trapezium, draw, fill=purple!15, trapezium left angle=70, trapezium right angle=110, minimum width=14mm, minimum height=8mm] at (@X@,@Y@) {};"),
]


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------
class LibShape:
    def __init__(self, name, libraries, template, thumb="", size_cm=(1, 1),
                 custom=False, packages=None):
        self.name = name
        self.libraries = libraries
        self.template = template
        self.thumb = thumb            # png path (may be "")
        self.size_cm = tuple(size_cm)
        self.custom = custom
        self.packages = packages or []
        self._rx = None

    def instantiate(self, x, y) -> str:
        from .elements import fnum
        return (self.template.replace("@X@", fnum(x)).replace("@Y@", fnum(y))
                + f" % lib:{self.name}")

    def match(self, stmt: str):
        """Return (x, y) if `stmt` (marker stripped) matches the template."""
        if self._rx is None:
            pat = re.escape(self.template)
            pat = pat.replace(re.escape("@X@"), f"({NUM})")
            pat = pat.replace(re.escape("@Y@"), f"({NUM})")
            pat = pat.replace(r"\ ", r"\s+")
            self._rx = re.compile(pat, re.S)
        m = self._rx.fullmatch(stmt.strip())
        if not m:
            return None
        return float(m.group(1)), float(m.group(2))

    def to_json(self):
        return {"name": self.name, "libraries": self.libraries,
                "template": self.template, "thumb": self.thumb,
                "size_cm": list(self.size_cm), "custom": self.custom,
                "packages": self.packages}


class Registry:
    def __init__(self):
        self.shapes = {}            # name -> LibShape

    def get(self, name):
        return self.shapes.get(name)

    def add(self, shape: LibShape):
        self.shapes[shape.name] = shape

    # persistence ----------------------------------------------------------
    def load(self):
        path = os.path.join(LIB_DIR, "library.json")
        if not os.path.exists(path):
            return False
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for d in data:
                if d.get("thumb") and not os.path.exists(d["thumb"]):
                    d["thumb"] = ""
                self.add(LibShape(**d))
            return bool(self.shapes)
        except (json.JSONDecodeError, TypeError, OSError):
            return False

    def save(self):
        os.makedirs(LIB_DIR, exist_ok=True)
        with open(os.path.join(LIB_DIR, "library.json"), "w",
                  encoding="utf-8") as f:
            json.dump([s.to_json() for s in self.shapes.values()], f, indent=1)


REGISTRY = Registry()


# ----------------------------------------------------------------------
# Compilation helpers
# ----------------------------------------------------------------------
def _preamble(libraries, packages=None):
    lines = ["\\documentclass[tikz,border=1.5pt]{standalone}"]
    for p in packages or []:
        lines.append(f"\\usepackage{{{p}}}")
    libs = sorted(set(libraries))
    if libs:
        lines.append("\\usetikzlibrary{" + ",".join(libs) + "}")
    return "\n".join(lines)


def _render_pngs(workdir, pdf="lib.pdf", prefix="el"):
    """PDF -> transparent PNGs; returns sorted list of files."""
    subprocess.run(["pdftocairo", "-png", "-transp", "-r", str(THUMB_DPI),
                    pdf, prefix], cwd=workdir, capture_output=True,
                   timeout=120, check=True)
    return sorted(f for f in os.listdir(workdir)
                  if f.startswith(prefix) and f.endswith(".png"))


def compile_catalog(entries, progress=None):
    """Compile all catalog entries in ONE document (fast); store thumbnails.

    Returns (list_of_LibShape, error_message_or_empty).
    """
    import tempfile
    os.makedirs(LIB_DIR, exist_ok=True)
    all_libs = [l for _, libs, _ in entries for l in libs]
    figs = []
    for name, libs, tpl in entries:
        body = tpl.replace("@X@", "0").replace("@Y@", "0")
        figs.append(f"\\begin{{tikzpicture}}\n{body}\n\\end{{tikzpicture}}")
    doc = (_preamble(all_libs) + "\n\\begin{document}\n"
           + "\n".join(figs) + "\n\\end{document}\n")

    with tempfile.TemporaryDirectory(prefix="tikzstudio_lib_") as wd:
        with open(os.path.join(wd, "lib.tex"), "w", encoding="utf-8") as f:
            f.write(doc)
        if progress:
            progress("Compiling element library with pdflatex…")
        proc = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
             "lib.tex"], cwd=wd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            return [], proc.stdout[-2500:]
        if progress:
            progress("Rendering element thumbnails…")
        try:
            pngs = _render_pngs(wd)
        except (subprocess.CalledProcessError, FileNotFoundError,
                subprocess.TimeoutExpired) as e:
            return [], f"pdftocairo failed: {e}"
        if len(pngs) != len(entries):
            return [], (f"Expected {len(entries)} thumbnails, "
                        f"got {len(pngs)}.")
        shapes = []
        from PyQt6.QtGui import QImage
        for (name, libs, tpl), png in zip(entries, pngs):
            safe = re.sub(r"[^a-z0-9]+", "_", name.lower())
            dest = os.path.join(LIB_DIR, f"{safe}.png")
            shutil.copy(os.path.join(wd, png), dest)
            img = QImage(dest)
            size_cm = (img.width() / PX_PER_CM, img.height() / PX_PER_CM)
            shapes.append(LibShape(name, libs, tpl, dest, size_cm))
    return shapes, ""


def compile_custom(name, code, libraries, packages, extra_preamble=""):
    """Test-compile one user element and create its thumbnail.

    `code` is TikZ drawn around the origin.  If it contains no @X@/@Y@
    placeholders it is wrapped in a shifted scope automatically.
    Returns (LibShape or None, error_message).
    """
    import tempfile
    code = code.strip()
    if "@X@" not in code:
        inner = code if code.endswith(";") or code.endswith("}") else code + ";"
        code = ("\\begin{scope}[shift={(@X@,@Y@)}]\n  "
                + inner.replace("\n", "\n  ")
                + "\n\\end{scope}")
    body = code.replace("@X@", "0").replace("@Y@", "0")
    pre = _preamble(libraries, packages)
    if extra_preamble.strip():
        pre += "\n" + extra_preamble.strip()
    doc = (pre + "\n\\begin{document}\n\\begin{tikzpicture}\n"
           + body + "\n\\end{tikzpicture}\n\\end{document}\n")

    with tempfile.TemporaryDirectory(prefix="tikzstudio_custom_") as wd:
        with open(os.path.join(wd, "lib.tex"), "w", encoding="utf-8") as f:
            f.write(doc)
        proc = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
             "lib.tex"], cwd=wd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            m = re.search(r"^! (.+)$", proc.stdout, re.M)
            return None, ("LaTeX error: " + m.group(1) if m
                          else proc.stdout[-2000:])
        try:
            pngs = _render_pngs(wd)
        except (subprocess.CalledProcessError, FileNotFoundError,
                subprocess.TimeoutExpired) as e:
            return None, f"pdftocairo failed: {e}"
        if not pngs:
            return None, "No thumbnail produced."
        os.makedirs(LIB_DIR, exist_ok=True)
        safe = "custom_" + re.sub(r"[^a-z0-9]+", "_", name.lower())
        dest = os.path.join(LIB_DIR, f"{safe}.png")
        shutil.copy(os.path.join(wd, pngs[0]), dest)
        from PyQt6.QtGui import QImage
        img = QImage(dest)
        size_cm = (img.width() / PX_PER_CM, img.height() / PX_PER_CM)
    return LibShape(name, libraries, code, dest, size_cm,
                    custom=True, packages=packages), ""


# ----------------------------------------------------------------------
# Background first-run worker
# ----------------------------------------------------------------------
class LibraryBuilder(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)   # ok, error

    def run(self):
        if shutil.which("pdflatex") is None:
            self.finished.emit(False, "pdflatex not found — element "
                               "thumbnails unavailable (install texlive).")
            return
        customs = [s for s in REGISTRY.shapes.values() if s.custom]
        shapes, err = compile_catalog(CATALOG, self.progress.emit)
        if err:
            self.finished.emit(False, err)
            return
        REGISTRY.shapes.clear()
        for s in shapes:
            REGISTRY.add(s)
        for s in customs:                      # keep user elements
            REGISTRY.add(s)
        REGISTRY.save()
        self.finished.emit(True, "")
