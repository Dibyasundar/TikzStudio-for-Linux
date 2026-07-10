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

import base64
import json
import os
import re
import shutil
import subprocess

from PyQt6.QtCore import QObject, pyqtSignal

NUM = r"[-+]?\d*\.?\d+"
# custom elements & thumbnails live under XDG data (not cache) so they
# survive app updates and cache cleaning
DATA_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME",
                   os.path.expanduser("~/.local/share")),
    "tikzstudio")
LIB_DIR = os.path.join(DATA_DIR, "library")
CUSTOM_JSON = os.path.join(LIB_DIR, "custom_elements.json")
CACHE_DIR = DATA_DIR   # legacy alias
_OLD_LIB = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "tikzstudio", "library")
if not os.path.isdir(LIB_DIR) and os.path.isdir(_OLD_LIB):
    try:
        shutil.copytree(_OLD_LIB, LIB_DIR)
    except OSError:
        pass
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
    ("star 6",             ["shapes.geometric"], _node("star", "star points=6")),
    ("star path",          [],
     "\\draw[shift={(@X@,@Y@)}] (90:0.5) \\foreach \\i in {1,...,5} "
     "{ -- (90+\\i*36+18:0.22) -- (90+\\i*72:0.5) } -- cycle;"),
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


CATEGORIES = {}
for _n, _l, _t in CATALOG:
    if "flow" in _n:
        CATEGORIES[_n] = "Flowchart"
    elif "path" in _n or _n == "brace":
        CATEGORIES[_n] = "Paths"
    elif "callout" in _n:
        CATEGORIES[_n] = "Callouts"
    elif "arrow" in _n:
        CATEGORIES[_n] = "Arrows"
    elif _n in ("cloud", "starburst", "signal", "tape", "forbidden sign",
                "magnifying glass"):
        CATEGORIES[_n] = "Symbols"
    elif _n in ("rounded rectangle", "chamfered rectangle", "cross out"):
        CATEGORIES[_n] = "Misc"
    else:
        CATEGORIES[_n] = "Geometric"


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------
class LibShape:
    def __init__(self, name, libraries, template, thumb="", size_cm=(1, 1),
                 custom=False, packages=None, group=""):
        self.name = name
        self.libraries = libraries
        self.template = template
        self.thumb = thumb            # png path (may be "")
        self.size_cm = tuple(size_cm)
        self.custom = custom
        self.packages = packages or []
        self.group = group or ("My elements" if custom else "Other")
        self._rx = None

    def instantiate(self, x, y) -> str:
        from .elements import fnum
        return (self.template.replace("@X@", fnum(x)).replace("@Y@", fnum(y))
                + f" % lib:{self.name}")

    def match_scoped(self, stmt: str):
        """Match the scope-wrapped (rotated/scaled) placement form.
        Returns (x, y, rotate, scale) or None."""
        inner = self.template.replace("@X@", "0").replace("@Y@", "0")
        body = (re.escape(inner).replace(r"\ ", r"\s+")
                .replace("\\\n", r"\s*"))
        pat = (r"\\begin\{scope\}\[shift=\{\((" + NUM + r"),(" + NUM
               + r")\)\}(?:,\s*rotate=(" + NUM + r"))?"
               + r"(?:,\s*scale=(" + NUM + r"))?\]\s*"
               + body + r"\s*\\end\{scope\}")
        m = re.fullmatch(pat, stmt.strip(), re.S)
        if not m:
            return None
        return (float(m.group(1)), float(m.group(2)),
                float(m.group(3) or 0.0), float(m.group(4) or 1.0))

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
                "packages": self.packages, "group": self.group}


class Registry:
    def __init__(self):
        self.shapes = {}            # name -> LibShape

    def get(self, name):
        return self.shapes.get(name)

    def add(self, shape: LibShape):
        self.shapes[shape.name] = shape

    # persistence ----------------------------------------------------------
    def _load_file(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return
        for d in data:
            if d.get("thumb") and not os.path.exists(d["thumb"]):
                d["thumb"] = ""
            try:
                sh = LibShape(**d)
            except TypeError:
                continue
            if not sh.custom and sh.group in ("", "Other") \
                    and sh.name in CATEGORIES:
                sh.group = CATEGORIES[sh.name]
            self.add(sh)

    def load(self):
        self._load_file(os.path.join(LIB_DIR, "library.json"))
        self._load_file(CUSTOM_JSON)
        return bool(self.shapes)

    def save(self):
        os.makedirs(LIB_DIR, exist_ok=True)
        builtins = [s.to_json() for s in self.shapes.values()
                    if not s.custom]
        customs = [s.to_json() for s in self.shapes.values() if s.custom]
        with open(os.path.join(LIB_DIR, "library.json"), "w",
                  encoding="utf-8") as f:
            json.dump(builtins, f, indent=1)
        with open(CUSTOM_JSON, "w", encoding="utf-8") as f:
            json.dump(customs, f, indent=1)


REGISTRY = Registry()


# ----------------------------------------------------------------------
# Import / export of custom elements
# ----------------------------------------------------------------------
def export_custom(path: str, group: str = None):
    """Write custom elements (optionally one group) to a JSON bundle."""
    import base64
    items = []
    for sh in REGISTRY.shapes.values():
        if not sh.custom:
            continue
        if group and sh.group != group:
            continue
        thumb_b64 = ""
        if sh.thumb and os.path.exists(sh.thumb):
            with open(sh.thumb, "rb") as f:
                thumb_b64 = base64.b64encode(f.read()).decode("ascii")
        items.append({"name": sh.name, "template": sh.template,
                      "libraries": sh.libraries, "packages": sh.packages,
                      "group": sh.group, "size_cm": list(sh.size_cm),
                      "thumb_b64": thumb_b64})
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"tikzstudio_elements": 1, "elements": items}, f, indent=1)
    return len(items)


def import_custom(path: str):
    """Load a JSON bundle of custom elements. Returns (count, error)."""
    import base64
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        items = data["elements"]
        assert data.get("tikzstudio_elements") == 1
    except (OSError, json.JSONDecodeError, KeyError, AssertionError) as e:
        return 0, f"Not a TikZ Studio element bundle: {e}"
    os.makedirs(LIB_DIR, exist_ok=True)
    n = 0
    for it in items:
        try:
            thumb = ""
            if it.get("thumb_b64"):
                safe = "custom_" + re.sub(r"[^a-z0-9]+", "_",
                                          it["name"].lower())
                thumb = os.path.join(LIB_DIR, f"{safe}.png")
                with open(thumb, "wb") as f:
                    f.write(base64.b64decode(it["thumb_b64"]))
            REGISTRY.add(LibShape(
                it["name"], it.get("libraries", []), it["template"],
                thumb, tuple(it.get("size_cm", (1, 1))), custom=True,
                packages=it.get("packages", []),
                group=it.get("group", "My elements")))
            n += 1
        except (KeyError, OSError, ValueError):
            continue
    REGISTRY.save()
    return n, ""


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
            shapes.append(LibShape(name, libs, tpl, dest, size_cm,
                                   group=CATEGORIES.get(name, "Other")))
    return shapes, ""


def compile_custom(name, code, libraries, packages, extra_preamble="",
                   group="My elements"):
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
                    custom=True, packages=packages,
                    group=group or "My elements"), ""


# ----------------------------------------------------------------------
# Import / export of custom element bundles
# ----------------------------------------------------------------------
def export_bundle(path, shapes):
    """Write custom elements (with embedded thumbnails) to a .tikzlib."""
    data = []
    for sh in shapes:
        d = sh.to_json()
        if sh.thumb and os.path.exists(sh.thumb):
            with open(sh.thumb, "rb") as f:
                d["thumb_b64"] = base64.b64encode(f.read()).decode()
        d["thumb"] = ""
        data.append(d)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"tikzstudio_elements": 1, "shapes": data}, f, indent=1)
    return len(data)


def import_bundle(path):
    """Load a .tikzlib bundle into the registry. Returns (added, skipped)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "shapes" not in data:
        raise ValueError("Not a TikZ Studio element bundle.")
    os.makedirs(LIB_DIR, exist_ok=True)
    added, skipped = [], []
    for d in data["shapes"]:
        b64 = d.pop("thumb_b64", "")
        name = d.get("name", "")
        existing = REGISTRY.get(name)
        if existing is not None:
            if existing.template == d.get("template"):
                skipped.append(name)
                continue
            i = 2
            while REGISTRY.get(f"{name} ({i})") is not None:
                i += 1
            name = f"{name} ({i})"
            d["name"] = name
        d["custom"] = True
        d["thumb"] = ""
        if b64:
            safe = "custom_" + re.sub(r"[^a-z0-9]+", "_", name.lower())
            dest = os.path.join(LIB_DIR, f"{safe}.png")
            with open(dest, "wb") as f:
                f.write(base64.b64decode(b64))
            d["thumb"] = dest
        try:
            REGISTRY.add(LibShape(**d))
            added.append(name)
        except TypeError:
            skipped.append(name)
    if added:
        REGISTRY.save()
    return added, skipped


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
