"""Expansion of \\foreach (and friends) into plain TikZ for rendering.

Handles for canvas rendering:
  \\foreach \\x in {1,2,3} {...}
  \\foreach \\x in {1,...,10} / {0,2,...,10} (dots notation, both ways)
  \\foreach \\x/\\y in {1/A, 2/B} (multi-variable)
  \\foreach \\x [evaluate=\\x as \\y using <expr>, count=\\i] in ... 
  \\breakforeach
  \\pgfplotsforeachungrouped (same syntax)
  \\pgfplotsinvokeforeach{list}{body with #1}
  \\ifnum / \\ifdim / \\ifcase ... \\or ... \\else ... \\fi inside bodies
The original statement is always preserved verbatim in the code; the
expansion is only used to build the canvas preview.
"""

import re
from typing import List, Optional

from .mathex import try_eval

NUM = r"[-+]?\d*\.?\d+"


def split_top(s: str, sep: str = ",") -> List[str]:
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if ch == sep and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def _fmt(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{round(v, 6):g}"


def expand_dots(items: List[str]) -> List[str]:
    """Expand pgffor dots notation: 1,...,5 / 0,2,...,10 / 5,...,1."""
    out: List[str] = []
    i = 0
    while i < len(items):
        it = items[i].strip()
        if it == "..." and out and i + 1 < len(items):
            start_txt = out[-1]
            prev_txt = out[-2] if len(out) >= 2 else None
            end_txt = items[i + 1].strip()
            a = try_eval(start_txt)
            b = try_eval(end_txt)
            if a is None or b is None:
                out.append(it)
                i += 1
                continue
            step = None
            if prev_txt is not None:
                p = try_eval(prev_txt)
                if p is not None and abs(a - p) > 1e-12:
                    step = a - p
            if step is None:
                step = 1.0 if b >= a else -1.0
            v = a + step
            n = 0
            while ((step > 0 and v <= b + 1e-9)
                   or (step < 0 and v >= b - 1e-9)) and n < 10000:
                out.append(_fmt(v))
                v += step
                n += 1
            i += 2          # consume '...' and the end item
        else:
            out.append(it)
            i += 1
    return out


def _resolve_conditionals(body: str) -> str:
    """Evaluate \\ifnum / \\ifdim / \\ifcase in an expanded body."""
    def _dim_cm(txt):
        m = re.fullmatch(rf"\s*({NUM})\s*(pt|mm|cm|in)?\s*", txt)
        if not m:
            return None
        v = float(m.group(1))
        u = m.group(2) or "cm"
        return v * {"pt": 0.035146, "mm": 0.1, "cm": 1.0, "in": 2.54}[u]

    for _ in range(20):
        m = re.search(
            rf"\\ifnum\s*({NUM})\s*([=<>])\s*({NUM})\s*(.*?)"
            r"(?:\\else(.*?))?\\fi", body, re.S)
        if m:
            a, op, b = float(m.group(1)), m.group(2), float(m.group(3))
            ok = (a == b) if op == "=" else (a < b) if op == "<" else a > b
            repl = m.group(4) if ok else (m.group(5) or "")
            body = body[:m.start()] + repl + body[m.end():]
            continue
        m = re.search(
            rf"\\ifdim\s*({NUM}\s*(?:pt|mm|cm|in)?)\s*([=<>])"
            rf"\s*({NUM}\s*(?:pt|mm|cm|in)?)\s*(.*?)"
            r"(?:\\else(.*?))?\\fi", body, re.S)
        if m:
            a, b = _dim_cm(m.group(1)), _dim_cm(m.group(3))
            op = m.group(2)
            if a is None or b is None:
                break
            ok = (abs(a - b) < 1e-9) if op == "=" else \
                (a < b) if op == "<" else a > b
            repl = m.group(4) if ok else (m.group(5) or "")
            body = body[:m.start()] + repl + body[m.end():]
            continue
        m = re.search(rf"\\ifcase\s*({NUM})\s*(.*?)\\fi", body, re.S)
        if m:
            idx = int(float(m.group(1)))
            inner = m.group(2)
            parts = re.split(r"\\or\b", inner)
            default = ""
            if parts and "\\else" in parts[-1]:
                parts[-1], default = parts[-1].split("\\else", 1)
            repl = parts[idx] if 0 <= idx < len(parts) else default
            body = body[:m.start()] + repl + body[m.end():]
            continue
        break
    return body


def brace_group(s: str, i: int):
    """Return (content, end_index) of the {..} group starting at s[i]."""
    assert s[i] == "{"
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    return None, len(s)


def expand_foreach(stmt: str) -> Optional[str]:
    """Expand a \\foreach-family statement into plain TikZ statements.
    Returns None if the statement cannot be expanded."""
    s = stmt.strip()

    m = re.match(r"\\pgfplotsinvokeforeach\s*{", s)
    if m:
        lst, j = brace_group(s, m.end() - 1)
        s2 = s[j:].lstrip()
        if not s2.startswith("{"):
            return None
        body, _ = brace_group(s2, 0)
        items = expand_dots(split_top(lst))
        out = []
        for it in items:
            out.append(_resolve_conditionals(body.replace("#1", it.strip())))
        return "\n".join(out)

    m = re.match(
        r"\\(?:foreach|pgfplotsforeachungrouped)\s*"
        r"(?P<vars>(?:\\[A-Za-z]+\s*/?\s*)+)"
        r"(?:\[(?P<opts>[^\]]*)\])?\s*in\s*{", s)
    if not m:
        return None
    lst, j = brace_group(s, m.end() - 1)
    s2 = s[j:].lstrip()
    if not s2.startswith("{"):
        return None
    body, _ = brace_group(s2, 0)

    varnames = [v.strip() for v in m.group("vars").split("/") if v.strip()]
    # options: evaluate=\x as \y using expr ; count=\i (from n)?
    evals, counts = [], []
    for opt in split_top(m.group("opts") or ""):
        opt = opt.strip()
        me = re.fullmatch(
            r"evaluate\s*=\s*(\\[A-Za-z]+)\s+as\s+(\\[A-Za-z]+)"
            r"\s+using\s+(.*)", opt, re.S)
        if me:
            evals.append((me.group(1), me.group(2), me.group(3)))
            continue
        mc = re.fullmatch(
            rf"count\s*=\s*(\\[A-Za-z]+)(?:\s+from\s+({NUM}))?", opt)
        if mc:
            counts.append((mc.group(1), float(mc.group(2) or 1)))

    items = expand_dots(split_top(lst))
    out = []
    idx = 0
    for item in items:
        idx += 1
        vals = [v.strip() for v in split_top(item, "/")]
        sub = {}
        for k, var in enumerate(varnames):
            sub[var] = vals[k] if k < len(vals) else (
                vals[-1] if vals else "")
        for cvar, start in counts:
            sub[cvar] = _fmt(start + idx - 1)
        for src, dst, exprtpl in evals:
            expr = exprtpl
            for var, val in sub.items():
                expr = re.sub(re.escape(var) + r"(?![A-Za-z])", val, expr)
            v = try_eval(expr)
            sub[dst] = _fmt(v) if v is not None else "0"
        b = body
        # longest names first so \xx is not clobbered by \x
        for var in sorted(sub, key=len, reverse=True):
            b = re.sub(re.escape(var) + r"(?![A-Za-z])", sub[var], b)
        b = _resolve_conditionals(b)
        stop = "\\breakforeach" in b
        b = b.replace("\\breakforeach", "")
        if b.strip():
            out.append(b.strip())
        if stop:
            break
    return "\n".join(out)
