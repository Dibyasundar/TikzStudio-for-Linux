"""A small, safe pgfmath expression evaluator.

Supports the parts of pgfmath that appear in coordinates and loops:
arithmetic (+ - * / ^), parentheses, comparisons (== != < > <= >=),
logic (&& || !), the ternary `cond ? a : b`, ifthenelse(c,a,b), and
common functions with pgf semantics (trig in DEGREES).
"""

import math
import re

_FUNCS = {
    "sin": lambda x: math.sin(math.radians(x)),
    "cos": lambda x: math.cos(math.radians(x)),
    "tan": lambda x: math.tan(math.radians(x)),
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
    "sqrt": math.sqrt, "abs": abs, "exp": math.exp,
    "ln": math.log, "log10": math.log10, "log2": math.log2,
    "floor": math.floor, "ceil": math.ceil, "round": round,
    "int": lambda x: float(int(x)), "mod": math.fmod,
    "min": min, "max": max, "pow": pow,
    "ifthenelse": lambda c, a, b: a if c else b,
    "veclen": lambda x, y: math.hypot(x, y),
    "sign": lambda x: (x > 0) - (x < 0),
    "random": lambda *a: 0.5,          # deterministic for rendering
    "rnd": lambda: 0.5,
    "true": 1.0, "false": 0.0,
}
_CONSTS = {"pi": math.pi, "e": math.e}

_ALLOWED = re.compile(
    r"^[\d\s.+\-*/%^(),<>=!&|?:a-zA-Z_]*$")
_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


def _split_ternary(s: str):
    """Split a top-level `cond ? a : b`; returns (cond, a, b) or None."""
    depth = 0
    qpos = None
    for i, ch in enumerate(s):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "?" and depth == 0 and qpos is None:
            qpos = i
        elif ch == ":" and depth == 0 and qpos is not None:
            return s[:qpos], s[qpos + 1:i], s[i + 1:]
    return None


def eval_expr(expr: str) -> float:
    """Evaluate a pgfmath expression. Raises ValueError on failure."""
    s = expr.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()
    if not s:
        raise ValueError("empty expression")
    t = _split_ternary(s)
    if t is not None:
        cond, a, b = t
        return eval_expr(a) if eval_expr(cond) != 0 else eval_expr(b)
    if not _ALLOWED.match(s):
        raise ValueError(f"disallowed characters in {expr!r}")
    # verify every name is known BEFORE any rewriting
    for name in set(_NAME.findall(s)):
        if name not in _FUNCS and name not in _CONSTS \
                and name not in ("and", "or", "not"):
            raise ValueError(f"unknown name {name!r} in {expr!r}")
    py = s.replace("^", "**")
    py = py.replace("&&", " and ").replace("||", " or ")
    py = re.sub(r"!(?!=)", " not ", py)
    ns = dict(_FUNCS)
    ns.update(_CONSTS)
    try:
        v = eval(py, {"__builtins__": {}}, ns)   # noqa: S307 (sanitised)
    except Exception as exc:
        raise ValueError(f"cannot evaluate {expr!r}: {exc}") from exc
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    return float(v)


def try_eval(expr: str):
    """eval_expr returning None instead of raising."""
    try:
        return eval_expr(expr)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None
