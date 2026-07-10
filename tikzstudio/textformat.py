"""Parse and apply LaTeX text formatting wrappers on node text.

Handles nested outer wrappers in any order:
  \\textbf{..} \\textit{..} \\underline{..} \\textcolor{col}{..}
and a leading size command (\\tiny .. \\Huge).
"""

import re
from dataclasses import dataclass

SIZE_PTS = {"tiny": 6, "scriptsize": 7, "footnotesize": 8, "small": 8.5,
            "normalsize": 9, "large": 10.5, "Large": 12, "LARGE": 14,
            "huge": 17, "Huge": 20}
SIZES = list(SIZE_PTS)


@dataclass
class TextFormat:
    inner: str = ""
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str = ""
    size: str = "normalsize"


def parse_format(text: str) -> TextFormat:
    f = TextFormat()
    t = text.strip()
    changed = True
    while changed:
        changed = False
        m = re.fullmatch(r"\\textbf\{(.*)\}", t, re.S)
        if m:
            f.bold = True; t = m.group(1).strip(); changed = True; continue
        m = re.fullmatch(r"\\textit\{(.*)\}", t, re.S)
        if m:
            f.italic = True; t = m.group(1).strip(); changed = True; continue
        m = re.fullmatch(r"\\underline\{(.*)\}", t, re.S)
        if m:
            f.underline = True; t = m.group(1).strip(); changed = True
            continue
        m = re.fullmatch(r"\\textcolor\{([^{}]*)\}\{(.*)\}", t, re.S)
        if m:
            f.color = m.group(1).strip(); t = m.group(2).strip()
            changed = True; continue
        m = re.fullmatch(r"\{\\(" + "|".join(SIZES) + r")\s+(.*)\}", t, re.S)
        if m:
            f.size = m.group(1); t = m.group(2).strip(); changed = True
            continue
        # legacy two-letter switches: {\bf x}, {\it x}, {\em x},
        # and prefix forms  \bf x  /  \it x
        m = re.fullmatch(r"\{\\bf\s+(.*)\}", t, re.S) \
            or re.fullmatch(r"\\bf\s+(.*)", t, re.S)
        if m:
            f.bold = True; t = m.group(1).strip(); changed = True; continue
        m = re.fullmatch(r"\{\\(?:it|em)\s+(.*)\}", t, re.S) \
            or re.fullmatch(r"\\(?:it|em)\s+(.*)", t, re.S)
        if m:
            f.italic = True; t = m.group(1).strip(); changed = True
            continue
    f.inner = t
    return f


def apply_format(f: TextFormat) -> str:
    """Rebuild the node text with canonical wrapper nesting."""
    t = f.inner
    if f.italic:
        t = f"\\textit{{{t}}}"
    if f.bold:
        t = f"\\textbf{{{t}}}"
    if f.underline:
        t = f"\\underline{{{t}}}"
    if f.color:
        t = f"\\textcolor{{{f.color}}}{{{t}}}"
    if f.size and f.size != "normalsize":
        t = f"{{\\{f.size} {t}}}"
    return t
