"""Parse TikZ code back into Elements (code -> canvas direction).

The parser handles the subset of TikZ that TikZ Studio itself generates
plus common hand-written variants.  Any statement it cannot understand is
kept as a RawElement so no user code is ever lost.
"""

import re
from typing import List, Optional, Tuple

from .elements import (Style, Element, LineEl, RectEl, CircleEl, EllipseEl,
                       PolyEl, BezierEl, PlotEl, ArcEl, GridEl, NodeEl,
                       ImageEl, RawEl, LibraryEl, GroupEl, CurveEl, PgfEl,
                       AxisEl, Figure, TikzDocument)

NUM = r"[-+]?\d*\.?\d+"
PT = rf"\(\s*({NUM})\s*,\s*({NUM})\s*\)"


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def split_statements(body: str) -> List[str]:
    """Split a tikzpicture body into statements.

    * statements end with ';' at brace/bracket depth 0
    * \\begin{scope}...\\end{scope} blocks count as ONE statement
    * a comment on the same line after ';' is attached to that statement
      (used for the "% lib:name" markers of library elements)
    """
    stmts, cur, depth = [], "", 0
    i, n = 0, len(body)
    while i < n:
        if body.startswith("\\pgf", i) and not cur.strip():
            j = body.find("\n", i)
            e = body.find(";", i)
            if e != -1 and (j == -1 or e < j):
                j = e + 1
            elif j == -1:
                j = n
            stmts.append(body[i:j].rstrip(";").strip())
            i = j
            continue
        if body.startswith("\\begin{scope}", i) and not cur.strip():
            # find the MATCHING \\end{scope} (scopes can nest)
            depth_s, j = 0, i
            while j < n:
                if body.startswith("\\begin{scope}", j):
                    depth_s += 1
                    j += 13
                elif body.startswith("\\end{scope}", j):
                    depth_s -= 1
                    j += 11
                    if depth_s == 0:
                        break
                else:
                    j += 1
            if depth_s == 0 and j <= n:
                stmt = body[i:j]
                i = j
                # trailing comment?
                k = i
                while k < n and body[k] in " \t":
                    k += 1
                if k < n and body[k] == "%":
                    e = body.find("\n", k)
                    e = n if e == -1 else e
                    stmt += " " + body[k:e].strip()
                    i = e
                stmts.append(stmt.strip())
                continue
        ch = body[i]
        if ch == "%":                       # comment
            j = body.find("\n", i)
            j = n if j == -1 else j
            if cur.strip():
                cur += body[i:j]
            else:
                stmts.append(body[i:j])
            i = j + 1
            continue
        cur += ch
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ";" and depth == 0:
            # attach same-line trailing comment (lib markers)
            k = i + 1
            while k < n and body[k] in " \t":
                k += 1
            if k < n and body[k] == "%":
                e = body.find("\n", k)
                e = n if e == -1 else e
                cur += " " + body[k:e].strip()
                i = e
            stmts.append(cur.strip())
            cur = ""
        i += 1
    if cur.strip():
        stmts.append(cur.strip())
    return [st for st in stmts if st.strip()]


def split_top_commas(s: str) -> List[str]:
    out, cur, depth = [], "", 0
    for ch in s:
        if ch in "{([":
            depth += 1
        elif ch in "})]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def dim_to_cm(txt: str):
    """'2cm' / '15mm' / '10pt' / '1in' / bare number -> cm (or None)."""
    m = re.fullmatch(rf"\s*({NUM})\s*(cm|mm|pt|in|ex|em)?\s*", txt)
    if not m:
        return None
    v = float(m.group(1))
    unit = m.group(2) or "cm"
    return v * {"cm": 1.0, "mm": 0.1, "pt": 0.035146, "in": 2.54,
                "ex": 0.15, "em": 0.35}[unit]


KNOWN_COLORS = {"black", "white", "red", "green", "blue", "cyan", "magenta",
                "yellow", "gray", "grey", "darkgray", "lightgray", "brown",
                "lime", "olive", "orange", "pink", "purple", "teal", "violet"}


def parse_options(opt: str, style: Style,
                  transforms: bool = True) -> List[str]:
    """Fill `style` from an option string; return options we did not use.

    With transforms=True, coordinate-transform keys (shift, xshift,
    yshift, rotate, scale, xscale, yscale) are captured into the style;
    nodes pass transforms=False because those keys mean node-local
    scaling/rotation there.
    """
    leftovers = []
    for item in split_top_commas(opt):
        it = item.strip()
        low = it.lower()
        if transforms:
            m = re.fullmatch(
                rf"shift\s*=\s*\{{\(\s*({NUM})\s*,\s*({NUM})\s*\)\}}", it)
            if m:
                style.tf_x += float(m.group(1))
                style.tf_y += float(m.group(2))
                continue
            m = re.fullmatch(rf"xshift\s*=\s*({NUM})\s*(cm|mm|pt|in)?", it)
            if m:
                d = dim_to_cm(it.split("=", 1)[1])
                if d is not None:
                    style.tf_x += d
                    continue
            m = re.fullmatch(rf"yshift\s*=\s*({NUM})\s*(cm|mm|pt|in)?", it)
            if m:
                d = dim_to_cm(it.split("=", 1)[1])
                if d is not None:
                    style.tf_y += d
                    continue
            m = re.fullmatch(rf"rotate\s*=\s*({NUM})", it)
            if m:
                style.tf_rot += float(m.group(1))
                continue
            m = re.fullmatch(rf"scale\s*=\s*({NUM})", it)
            if m:
                style.tf_sx *= float(m.group(1))
                style.tf_sy *= float(m.group(1))
                continue
            m = re.fullmatch(rf"xscale\s*=\s*({NUM})", it)
            if m:
                style.tf_sx *= float(m.group(1))
                continue
            m = re.fullmatch(rf"yscale\s*=\s*({NUM})", it)
            if m:
                style.tf_sy *= float(m.group(1))
                continue
        TIP = (r"(?:<<|>>|<|>|\|" + ""
               r"|[Ss]tealth|[Ll]atex|to"
               r"|\{[A-Za-z][A-Za-z ]*(?:\[[^\]]*\])?\})")
        if it != "-" and re.fullmatch(rf"{TIP}?-{TIP}?", it):
            style.arrows = it
        elif low in ("dashed", "dotted", "solid", "dash dot",
                     "dash dot dot", "densely dashed", "densely dotted",
                     "loosely dashed", "loosely dotted"):
            style.dash = low
        elif low.startswith("dash pattern="):
            style.dash = it
        elif low.startswith("color="):
            style.draw = it[6:].strip()
        elif low.startswith("draw=") :
            style.draw = it[5:].strip()
        elif low.startswith("fill="):
            style.fill = it[5:].strip()
        elif low.startswith("line width="):
            m = re.match(rf"line width\s*=\s*({NUM})\s*pt?", it, re.I)
            if m:
                style.line_width = float(m.group(1))
            else:
                leftovers.append(it)
        elif low.startswith("draw opacity="):
            try:
                style.draw_opacity = float(it.split("=", 1)[1])
            except ValueError:
                leftovers.append(it)
        elif low.startswith("fill opacity="):
            try:
                style.fill_opacity = float(it.split("=", 1)[1])
            except ValueError:
                leftovers.append(it)
        elif low.startswith("opacity="):
            try:
                style.opacity = float(it.split("=", 1)[1])
            except ValueError:
                leftovers.append(it)
        elif low in ("thin", "thick", "very thick", "ultra thick",
                     "very thin", "ultra thin", "semithick"):
            style.line_width = {"ultra thin": 0.1, "very thin": 0.2,
                                "thin": 0.4, "semithick": 0.6, "thick": 0.8,
                                "very thick": 1.2, "ultra thick": 1.6}[low]
        elif it.split("!")[0] in KNOWN_COLORS or it.startswith("rgb,"):
            style.draw = it
        else:
            leftovers.append(it)
    return leftovers


def extract_opts(stmt: str, cmd: str) -> Tuple[str, str]:
    """Return (options, rest) for '\\cmd[opts] rest;'."""
    s = stmt[len(cmd):].lstrip()
    if s.startswith("["):
        depth, i = 0, 0
        for i, ch in enumerate(s):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    break
        return s[1:i], s[i + 1:].strip()
    return "", s


# ----------------------------------------------------------------------
# statement parsers
# ----------------------------------------------------------------------
def parse_statement(stmt: str) -> Element:
    try:
        el = _parse_statement(stmt)
        return el if el is not None else RawEl(code=stmt)
    except Exception:
        return RawEl(code=stmt)


LIB_MARK = re.compile(r"^(.*?)\s*%\s*lib:(.+?)\s*$", re.S)


def _parse_statement(stmt: str) -> Optional[Element]:
    s = stmt.strip()
    if s.startswith("%"):
        return RawEl(code=s)

    m = LIB_MARK.match(s)
    if m:
        from .library import REGISTRY
        shape = REGISTRY.get(m.group(2).strip())
        if shape is not None:
            xy = shape.match(m.group(1))
            if xy is not None:
                return LibraryEl(name=shape.name, template=shape.template,
                                 x=xy[0], y=xy[1])
            xys = shape.match_scoped(m.group(1))
            if xys is not None:
                return LibraryEl(name=shape.name, template=shape.template,
                                 x=xys[0], y=xys[1], rotate=xys[2],
                                 scale=xys[3])
        return RawEl(code=s)      # marker but unmatched -> keep verbatim

    if s.startswith("\\sbox{\\tzsplot}"):
        m = re.fullmatch(
            r"\\sbox\{\\tzsplot\}\{(?P<code>.*)\}\s*"
            r"\\node\[inner sep=0pt\] at "
            rf"\(\s*({NUM})\s*,\s*({NUM})\s*\)\s*"
            r"\{\\usebox\{\\tzsplot\}\}\s*;?", s, re.S)
        if m:
            return AxisEl(code=m.group("code").strip(),
                          x=float(m.group(2)), y=float(m.group(3)))
        return RawEl(code=s)
    if s.startswith("\\pgf"):
        return PgfEl(code=s, effect=parse_pgf(s))
    if s.startswith("\\begin{scope}"):
        return _parse_scope(s)
    if s.startswith("\\node"):
        return _parse_node(s)
    if not (s.startswith("\\draw") or s.startswith("\\filldraw")
            or s.startswith("\\fill") or s.startswith("\\path")):
        return None

    cmd = "\\" + re.match(r"\\(\w+)", s).group(1)
    opt, rest = extract_opts(s, cmd)
    style = Style()
    if cmd == "\\fill" or cmd == "\\filldraw":
        style.fill = "black"
    leftovers = parse_options(opt, style)
    rest = rest.rstrip(";").strip()

    # grid ---------------------------------------------------------------
    m = re.fullmatch(rf"{PT}\s+grid\s+{PT}", rest)
    if m:
        step = 0.5
        kept = []
        for lo in leftovers:
            mm = re.match(rf"step\s*=\s*({NUM})", lo)
            if mm:
                step = float(mm.group(1))
            else:
                kept.append(lo)
        style.extra = kept
        g = GridEl(style=style, step=step)
        g.x1, g.y1, g.x2, g.y2 = map(float, m.groups())
        return g

    style.extra = leftovers   # any other TikZ option: preserved verbatim

    # rectangle ------------------------------------------------------------
    m = re.fullmatch(rf"{PT}\s+rectangle\s+{PT}", rest)
    if m:
        r = RectEl(style=style)
        r.x1, r.y1, r.x2, r.y2 = map(float, m.groups())
        return r

    # circle ----------------------------------------------------------------
    m = re.fullmatch(rf"{PT}\s+circle\s*(?:\(\s*({NUM})\s*(?:cm)?\s*\)|\[radius\s*=\s*({NUM})\s*\])", rest)
    if m:
        c = CircleEl(style=style)
        c.cx, c.cy = float(m.group(1)), float(m.group(2))
        c.r = float(m.group(3) or m.group(4))
        return c

    # ellipse -----------------------------------------------------------------
    m = re.fullmatch(rf"{PT}\s+ellipse\s*\(\s*({NUM})\s*and\s*({NUM})\s*\)", rest)
    if m:
        e = EllipseEl(style=style)
        e.cx, e.cy, e.rx, e.ry = map(float, m.groups())
        return e

    # arc ------------------------------------------------------------------
    m = re.fullmatch(rf"{PT}\s+arc\s*\(\s*({NUM})\s*:\s*({NUM})\s*:\s*({NUM})\s*\)", rest)
    if m:
        import math
        sx, sy, a1, a2, r = map(float, m.groups())
        a = ArcEl(style=style, r=r, a1=a1, a2=a2)
        a.cx = sx - r * math.cos(math.radians(a1))
        a.cy = sy - r * math.sin(math.radians(a1))
        return a

    # bezier (single segment or chained N-point curve) -------------------------
    SEG = rf"\s*\.\.\s*controls\s*{PT}\s*and\s*{PT}\s*\.\.\s*{PT}"
    m = re.fullmatch(rf"{PT}(?:{SEG})+", rest)
    if m:
        nums = [float(a) for pair in re.findall(PT, rest) for a in pair]
        start = nums[:2]
        rest_nums = nums[2:]
        segs = [rest_nums[k:k + 6] for k in range(0, len(rest_nums), 6)]
        if len(segs) == 1:
            b = BezierEl(style=style)
            (b.x1, b.y1) = start
            (b.c1x, b.c1y, b.c2x, b.c2y, b.x2, b.y2) = segs[0]
            return b
        return CurveEl(style=style, x0=start[0], y0=start[1], segs=segs)

    # plot / freehand ---------------------------------------------------------
    m = re.fullmatch(r"plot\s*\[\s*smooth\s*\]\s*coordinates\s*\{(.*)\}", rest, re.S)
    if m:
        pts = re.findall(PT, m.group(1))
        if pts:
            return PlotEl(style=style, points=[(float(a), float(b)) for a, b in pts])

    # polyline / polygon / simple line -----------------------------------------
    if re.fullmatch(rf"{PT}(\s*--\s*{PT})+(\s*--\s*cycle)?", rest):
        closed = rest.rstrip().endswith("cycle")
        pts = [(float(a), float(b)) for a, b in re.findall(PT, rest)]
        if len(pts) == 2 and not closed:
            l = LineEl(style=style)
            (l.x1, l.y1), (l.x2, l.y2) = pts
            return l
        return PolyEl(style=style, points=pts, closed=closed)

    return None


PT_TO_CM = 0.035146


def _dim_pt(txt):
    d = dim_to_cm(txt)
    return None if d is None else d / PT_TO_CM


def _dash_list(txt):
    return [_dim_pt(m) for m in re.findall(r"\{([^{}]*)\}", txt)]


def parse_pgf(stmt: str) -> dict:
    """Parse a \\pgfset... / \\pgftransform... command into an effect."""
    s = stmt.strip().rstrip(";")
    eff = {}

    def m1(pat):
        m = re.fullmatch(pat, s)
        return m.groups() if m else None

    g = m1(r"\\pgfsetlinewidth\{([^{}]*)\}")
    if g:
        v = _dim_pt(g[0])
        if v is not None:
            eff["lw"] = v
        return eff
    g = m1(r"\\pgfsetinnerlinewidth\{([^{}]*)\}")
    if g:
        v = _dim_pt(g[0])
        if v is not None:
            eff["inner_lw"] = v
        return eff
    g = m1(r"\\pgfsetdash\{(.*)\}\{([^{}]*)\}")
    if g:
        eff["dash"] = _dash_list(g[0])
        eff["dash_phase"] = _dim_pt(g[1]) or 0.0
        return eff
    g = m1(r"\\pgfsetinnerdash\{(.*)\}\{([^{}]*)\}")
    if g:
        eff["inner_dash"] = _dash_list(g[0])
        return eff
    if s == "\\pgfsetbuttcap":
        return {"cap": "butt"}
    if s == "\\pgfsetroundcap":
        return {"cap": "round"}
    if s == "\\pgfsetrectcap":
        return {"cap": "rect"}
    if s == "\\pgfsetmiterjoin":
        return {"join": "miter"}
    if s == "\\pgfsetroundjoin":
        return {"join": "round"}
    if s == "\\pgfsetbeveljoin":
        return {"join": "bevel"}
    g = m1(r"\\pgfsetmiterlimit\{([^{}]*)\}")
    if g:
        try:
            return {"miterlimit": float(g[0])}
        except ValueError:
            return eff
    g = m1(r"\\pgfsetcolor\{(.*)\}")
    if g:
        return {"stroke": g[0], "fillc": g[0]}
    g = m1(r"\\pgfsetstrokecolor\{(.*)\}")
    if g:
        return {"stroke": g[0]}
    g = m1(r"\\pgfsetfillcolor\{(.*)\}")
    if g:
        return {"fillc": g[0]}
    g = m1(r"\\pgfsetstrokeopacity\{([^{}]*)\}")
    if g:
        try:
            return {"stroke_op": float(g[0])}
        except ValueError:
            return eff
    g = m1(r"\\pgfsetfillopacity\{([^{}]*)\}")
    if g:
        try:
            return {"fill_op": float(g[0])}
        except ValueError:
            return eff
    g = m1(r"\\pgfsetblendmode\{([^{}]*)\}")
    if g:
        return {"blend": g[0].strip().lower()}
    if s == "\\pgfsetnonzerorule":
        return {"eo": False}
    if s == "\\pgfseteorule":
        return {"eo": True}
    g = m1(r"\\pgfsetarrowsstart\{(.*)\}")
    if g:
        return {"astart": g[0].strip()}
    g = m1(r"\\pgfsetarrowsend\{(.*)\}")
    if g:
        return {"aend": g[0].strip()}
    g = m1(r"\\pgfsetshortenstart\{([^{}]*)\}")
    if g:
        d = dim_to_cm(g[0])
        return {"ss": d} if d is not None else eff
    g = m1(r"\\pgfsetshortenend\{([^{}]*)\}")
    if g:
        d = dim_to_cm(g[0])
        return {"se": d} if d is not None else eff
    # transforms ---------------------------------------------------------
    g = m1(r"\\pgftransformshift\{\\pgfpoint\{([^{}]*)\}\{([^{}]*)\}\}")
    if g:
        x, y = dim_to_cm(g[0]), dim_to_cm(g[1])
        if x is not None and y is not None:
            return {"tf": ("shift", x, y)}
        return eff
    g = m1(r"\\pgftransformscale\{([^{}]*)\}")
    if g:
        try:
            f = float(g[0]); return {"tf": ("scale", f, f)}
        except ValueError:
            return eff
    g = m1(r"\\pgftransformxscale\{([^{}]*)\}")
    if g:
        try:
            return {"tf": ("scale", float(g[0]), 1.0)}
        except ValueError:
            return eff
    g = m1(r"\\pgftransformyscale\{([^{}]*)\}")
    if g:
        try:
            return {"tf": ("scale", 1.0, float(g[0]))}
        except ValueError:
            return eff
    g = m1(r"\\pgftransformrotate\{([^{}]*)\}")
    if g:
        try:
            return {"tf": ("rotate", float(g[0]))}
        except ValueError:
            return eff
    return eff


def _parse_scope(s: str) -> Optional[Element]:
    m = re.fullmatch(
        r"\\begin\{scope\}\s*(?:\[(?P<opt>.*?)\])?\s*"
        r"(?P<body>.*)\\end\{scope\}\s*", s, re.S)
    if not m:
        return None
    x = y = rot = 0.0
    sc = xs = ys = 1.0
    for it in split_top_commas(m.group("opt") or ""):
        it = it.strip()
        if not it:
            continue
        mm = re.fullmatch(
            rf"shift\s*=\s*\{{\(\s*({NUM})\s*,\s*({NUM})\s*\)\}}", it)
        if mm:
            x, y = float(mm.group(1)), float(mm.group(2))
            continue
        mm = re.fullmatch(rf"(x|y)?shift\s*=\s*({NUM})\s*(cm|mm|pt|in)?", it)
        if mm:
            d = dim_to_cm(it.split("=", 1)[1])
            if d is not None:
                if it.startswith("x"):
                    x += d
                else:
                    y += d
                continue
        mm = re.fullmatch(rf"rotate\s*=\s*({NUM})", it)
        if mm:
            rot = float(mm.group(1))
            continue
        mm = re.fullmatch(rf"scale\s*=\s*({NUM})", it)
        if mm:
            sc = float(mm.group(1))
            continue
        mm = re.fullmatch(rf"xscale\s*=\s*({NUM})", it)
        if mm:
            xs = float(mm.group(1))
            continue
        mm = re.fullmatch(rf"yscale\s*=\s*({NUM})", it)
        if mm:
            ys = float(mm.group(1))
            continue
        return None            # unknown scope option -> keep raw
    return GroupEl(children=parse_body(m.group("body")), x=x, y=y, s=sc,
                   rot=rot, xs=xs, ys=ys)


def _parse_node(s: str) -> Optional[Element]:
    opt, rest = extract_opts(s, "\\node")
    m = re.fullmatch(rf"at\s*{PT}\s*\{{(.*)\}}\s*;?", rest.strip(), re.S)
    if not m:
        return None
    x, y, content = float(m.group(1)), float(m.group(2)), m.group(3)

    # image node? ({\includegraphics[opts]{path}})
    mi = re.fullmatch(
        r"\\includegraphics\s*(?:\[(?P<g>[^\]]*)\])?\{(?P<p>.+?)\}",
        content.strip(), re.S)
    if mi:
        img = ImageEl(x=x, y=y, path=mi.group("p"),
                      width=0.0, node_opts=opt.strip())
        for it in split_top_commas(mi.group("g") or ""):
            it = it.strip()
            low = it.lower()
            if low.startswith("width="):
                d = dim_to_cm(it.split("=", 1)[1])
                if d is not None:
                    img.width = d
                    continue
            elif low.startswith("height="):
                d = dim_to_cm(it.split("=", 1)[1])
                if d is not None:
                    img.height = d
                    continue
            elif low.startswith("scale="):
                try:
                    img.gscale = float(it.split("=", 1)[1]); continue
                except ValueError:
                    pass
            elif low.startswith("angle="):
                try:
                    img.angle = float(it.split("=", 1)[1]); continue
                except ValueError:
                    pass
            elif low == "keepaspectratio":
                img.keepaspect = True
                continue
            if it:
                img.gextra.append(it)
        return img

    style = Style()
    leftovers = parse_options(opt, style, transforms=False)
    node = NodeEl(style=style, x=x, y=y, text=content)
    POSITIONAL = {"above": "south", "below": "north", "left": "east",
                  "right": "west",
                  "above left": "south east", "above right": "south west",
                  "below left": "north east", "below right": "north west"}
    kept = []
    for lo in leftovers:
        low = lo.lower()
        if lo == "draw":
            node.draw_border = True
        elif lo in ("rectangle", "circle", "ellipse", "star",
                    "diamond", "regular polygon", "cloud",
                    "single arrow", "double arrow", "trapezium",
                    "signal", "tape", "starburst", "cylinder",
                    "kite", "dart", "ellipse callout",
                    "rectangle callout", "cloud callout"):
            node.shape = lo
        elif low.startswith("star points="):
            try:
                node.star_points = int(lo.split("=", 1)[1]); continue
            except ValueError:
                kept.append(lo)
        elif low.startswith("regular polygon sides="):
            try:
                node.poly_sides = int(lo.split("=", 1)[1]); continue
            except ValueError:
                kept.append(lo)
        elif low.startswith("inner sep="):
            d = dim_to_cm(lo.split("=", 1)[1])
            if d is not None:
                node.inner_sep = d
            else:
                kept.append(lo)
        elif re.fullmatch(
                rf"callout (absolute|relative) pointer=\{{\(\s*({NUM})"
                rf"\s*,\s*({NUM})\s*\)\}}", lo):
            mm = re.fullmatch(
                rf"callout (absolute|relative) pointer=\{{\(\s*({NUM})"
                rf"\s*,\s*({NUM})\s*\)\}}", lo)
            node.has_ptr = True
            node.ptr_rel = mm.group(1) == "relative"
            node.ptr_x = float(mm.group(2))
            node.ptr_y = float(mm.group(3))
        elif low.startswith("anchor="):
            node.anchor = lo.split("=", 1)[1].strip()
        elif low in POSITIONAL:
            node.anchor = POSITIONAL[low]
        elif low.startswith("rotate="):
            try:
                node.rotate = float(lo.split("=", 1)[1]); continue
            except ValueError:
                kept.append(lo)
        elif low.startswith("scale="):
            try:
                node.scale = float(lo.split("=", 1)[1]); continue
            except ValueError:
                kept.append(lo)
        elif low.startswith("minimum width="):
            d = dim_to_cm(lo.split("=", 1)[1])
            if d is not None:
                node.min_w = d
            else:
                kept.append(lo)
        elif low.startswith("minimum height="):
            d = dim_to_cm(lo.split("=", 1)[1])
            if d is not None:
                node.min_h = d
            else:
                kept.append(lo)
        elif low.startswith("minimum size="):
            d = dim_to_cm(lo.split("=", 1)[1])
            if d is not None:
                node.min_w = node.min_h = d
            else:
                kept.append(lo)
        elif low.startswith("text width="):
            d = dim_to_cm(lo.split("=", 1)[1])
            if d is not None:
                node.text_width = d
            else:
                kept.append(lo)
        elif low.startswith("align="):
            node.align = lo.split("=", 1)[1].strip()
        else:
            kept.append(lo)
    node.style.extra = kept       # everything else: preserved verbatim
    return node


# ----------------------------------------------------------------------
# figure / document level
# ----------------------------------------------------------------------
def parse_body(body: str) -> List[Element]:
    return [parse_statement(st) for st in split_statements(body)]


TIKZPIC_RE = re.compile(
    r"\\begin\{tikzpicture\}(\[[^\]]*\])?(.*?)\\end\{tikzpicture\}", re.S)


def import_tex(text: str) -> TikzDocument:
    """Import a full .tex file: preamble packages + all tikzpictures."""
    doc = TikzDocument()
    doc.figures = []
    doc.packages = []
    doc.tikz_libraries = []

    m = re.search(r"\\documentclass\[([^\]]*)\]\{standalone\}", text)
    if m:
        doc.doc_class_options = m.group(1)
    for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{([^}]*)\}", text):
        for p in m.group(1).split(","):
            if p.strip() and p.strip() != "tikz":
                doc.packages.append(p.strip())
    for m in re.finditer(r"\\usetikzlibrary\{([^}]*)\}", text):
        doc.tikz_libraries += [l.strip() for l in m.group(1).split(",") if l.strip()]
    if not doc.tikz_libraries:
        doc.tikz_libraries = ["arrows.meta"]

    for i, m in enumerate(TIKZPIC_RE.finditer(text), start=1):
        fig = Figure(name=f"figure{i}")
        fig.env_options = (m.group(1) or "").strip("[]")
        fig.elements = parse_body(m.group(2))
        doc.figures.append(fig)
    if not doc.figures:
        # bare .tikz body file (no environment): treat everything as body
        if re.search(r"\\(draw|node|fill|path|filldraw)\b", text):
            fig = Figure()
            fig.elements = parse_body(text)
            doc.figures.append(fig)
    if not doc.figures:
        doc.figures = [Figure()]
    return doc
