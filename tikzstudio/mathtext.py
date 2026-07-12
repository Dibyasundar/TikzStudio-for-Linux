"""Approximate LaTeX math -> Unicode for WYSIWYG node display.

The canvas cannot run TeX per keystroke, so node text is converted to a
Unicode approximation (Greek letters, operators, super/subscripts,
fractions).  The compiled PDF preview remains the exact rendering.
"""

import re

# AMS accents: rendered with Unicode combining marks
ACCENTS = {
    "hat": "\u0302", "widehat": "\u0302",
    "bar": "\u0304", "overline": "\u0305",
    "vec": "\u20d7", "overrightarrow": "\u20d7",
    "dot": "\u0307", "ddot": "\u0308", "dddot": "\u20db",
    "tilde": "\u0303", "widetilde": "\u0303",
    "check": "\u030c", "breve": "\u0306",
    "acute": "\u0301", "grave": "\u0300",
    "mathring": "\u030a", "underline": "\u0332",
}


def _apply_accents(s: str) -> str:
    def rep(m):
        inner = m.group(2)
        mark = ACCENTS[m.group(1)]
        if not inner:
            return ""
        # combining mark goes after EVERY base char for wide accents,
        # after the last char otherwise (good enough for canvas text)
        if m.group(1) in ("overline", "underline", "widehat",
                          "widetilde", "overrightarrow"):
            return "".join(ch + mark for ch in inner)
        return inner[:-1] + inner[-1] + mark
    pat = r"\\(" + "|".join(ACCENTS) + r")\{([^{}]*)\}"
    prev = None
    while prev != s:
        prev = s
        s = re.sub(pat, rep, s)
    return s



GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ",
    "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ",
    "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ",
    "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω",
}

SYMBOLS = {
    "times": "×", "div": "÷", "pm": "±", "mp": "∓", "cdot": "⋅",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "equiv": "≡", "sim": "∼", "simeq": "≃", "propto": "∝",
    "infty": "∞", "partial": "∂", "nabla": "∇", "sum": "∑", "prod": "∏",
    "int": "∫", "oint": "∮", "sqrt": "√", "rightarrow": "→", "to": "→",
    "leftarrow": "←", "Rightarrow": "⇒", "Leftarrow": "⇐",
    "leftrightarrow": "↔", "Leftrightarrow": "⇔", "mapsto": "↦",
    "uparrow": "↑", "downarrow": "↓", "in": "∈", "notin": "∉",
    "subset": "⊂", "supset": "⊃", "subseteq": "⊆", "supseteq": "⊇",
    "cup": "∪", "cap": "∩", "emptyset": "∅", "varnothing": "∅",
    "forall": "∀", "exists": "∃", "neg": "¬", "lnot": "¬",
    "wedge": "∧", "land": "∧", "vee": "∨", "lor": "∨",
    "oplus": "⊕", "otimes": "⊗", "ominus": "⊖", "odot": "⊙",
    "perp": "⊥", "parallel": "∥", "angle": "∠", "degree": "°",
    "circ": "∘", "bullet": "•", "star": "⋆", "dagger": "†",
    "prime": "′", "hbar": "ℏ", "ell": "ℓ", "Re": "ℜ", "Im": "ℑ",
    "aleph": "ℵ", "dots": "…", "ldots": "…", "cdots": "⋯", "vdots": "⋮",
    "quad": "  ", "qquad": "    ", ",": " ", ";": " ", "!": "",
    "langle": "⟨", "rangle": "⟩", "lfloor": "⌊", "rfloor": "⌋",
    "lceil": "⌈", "rceil": "⌉", "%": "%", "&": "&", "#": "#", "_": "_",
    "{": "{", "}": "}",
}

SUP = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵",
       "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻",
       "(": "⁽", ")": "⁾", "n": "ⁿ", "i": "ⁱ", "=": "⁼", "T": "ᵀ",
       "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "k": "ᵏ",
       "m": "ᵐ", "o": "ᵒ", "p": "ᵖ", "t": "ᵗ", "x": "ˣ", "*": "*"}
SUB = {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅",
       "6": "₆", "7": "₇", "8": "₈", "9": "₉", "+": "₊", "-": "₋",
       "(": "₍", ")": "₎", "=": "₌", "a": "ₐ", "e": "ₑ", "h": "ₕ",
       "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ",
       "o": "ₒ", "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ",
       "v": "ᵥ", "x": "ₓ"}


def _script(chars: str, table: dict, mark: str) -> str:
    if all(c in table for c in chars):
        return "".join(table[c] for c in chars)
    return mark + (chars if len(chars) == 1 else "{" + chars + "}")


def latex_to_unicode(text: str) -> str:
    text = _apply_accents(text)
    for _k, _v in _BRACED_SYMBOLS.items():
        text = text.replace("\\" + _k, _v)
    """Convert LaTeX-ish node text into displayable Unicode."""
    s = text

    # \frac{a}{b} -> a/b  (repeat for nesting)
    frac = re.compile(r"\\[td]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
    for _ in range(4):
        s2 = frac.sub(lambda m: f"{m.group(1)}/{m.group(2)}", s)
        if s2 == s:
            break
        s = s2

    # \sqrt{x} -> √(x) ; \sqrt x -> √x
    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", lambda m: "√(" + m.group(1) + ")", s)

    # \text{..}, \mathrm{..}, \mathbf{..} etc -> contents
    s = re.sub(r"\\(?:text|mathrm|mathbf|mathit|mathsf|mathcal|mathbb|"
               r"textbf|textit|operatorname)\s*\{([^{}]*)\}",
               lambda m: m.group(1), s)

    # symbols & greek (longest names first)
    table = {**SYMBOLS, **GREEK}
    for name in sorted(table, key=len, reverse=True):
        if name.isalpha():
            s = re.sub(r"\\" + name + r"(?![A-Za-z])", table[name], s)
        else:
            s = s.replace("\\" + name, table[name])

    # super / subscripts
    s = re.sub(r"\^\{([^{}]*)\}", lambda m: _script(m.group(1), SUP, "^"), s)
    s = re.sub(r"_\{([^{}]*)\}", lambda m: _script(m.group(1), SUB, "_"), s)
    s = re.sub(r"\^(\S)", lambda m: _script(m.group(1), SUP, "^"), s)
    s = re.sub(r"_(\S)", lambda m: _script(m.group(1), SUB, "_"), s)

    # leftover latex commands: keep the bare name
    s = re.sub(r"\\([A-Za-z]+)", lambda m: m.group(1), s)
    s = s.replace("$", "")
    s = re.sub(r"[{}]", "", s)
    return s


# --- AMS / extra symbols (additive) -----------------------------------
_EXTRA_SYMBOLS = {
    "implies": "⟹", "impliedby": "⟸", "iff": "⟺", "mapsto": "↦",
    "longmapsto": "⟼", "longrightarrow": "⟶", "longleftarrow": "⟵",
    "hookrightarrow": "↪", "hookleftarrow": "↩", "rightharpoonup": "⇀",
    "leftharpoonup": "↼", "rightleftharpoons": "⇌", "nearrow": "↗",
    "searrow": "↘", "nwarrow": "↖", "swarrow": "↙", "uparrow": "↑",
    "downarrow": "↓", "updownarrow": "↕", "Uparrow": "⇑",
    "Downarrow": "⇓", "curvearrowright": "↷", "curvearrowleft": "↶",
    "approx": "≈", "equiv": "≡", "sim": "∼", "simeq": "≃",
    "cong": "≅", "propto": "∝", "perp": "⊥", "parallel": "∥",
    "mid": "∣", "nmid": "∤", "ll": "≪", "gg": "≫", "asymp": "≍",
    "doteq": "≐", "triangleq": "≜", "prec": "≺", "succ": "≻",
    "preceq": "⪯", "succeq": "⪰", "vdash": "⊢", "dashv": "⊣",
    "models": "⊨", "top": "⊤", "bot": "⊥",
    "cup": "∪", "cap": "∩", "setminus": "∖", "in": "∈",
    "notin": "∉", "ni": "∋", "subset": "⊂", "supset": "⊃",
    "subseteq": "⊆", "supseteq": "⊇", "subsetneq": "⊊",
    "supsetneq": "⊋", "sqsubseteq": "⊑", "sqsupseteq": "⊒",
    "emptyset": "∅", "varnothing": "∅",
    "oplus": "⊕", "ominus": "⊖", "otimes": "⊗", "oslash": "⊘",
    "odot": "⊙", "boxplus": "⊞", "boxtimes": "⊠",
    "pm": "±", "mp": "∓", "cdot": "⋅", "bullet": "•", "star": "⋆",
    "circ": "∘", "ast": "∗", "dagger": "†", "ddagger": "‡",
    "wedge": "∧", "vee": "∨", "neg": "¬", "lnot": "¬",
    "forall": "∀", "exists": "∃", "nexists": "∄",
    "aleph": "ℵ", "beth": "ℶ", "hbar": "ℏ", "ell": "ℓ",
    "Re": "ℜ", "Im": "ℑ", "wp": "℘", "nabla": "∇", "partial": "∂",
    "angle": "∠", "measuredangle": "∡", "sphericalangle": "∢",
    "triangle": "△", "square": "□", "blacksquare": "■",
    "Diamond": "◇", "lozenge": "◊",
    "langle": "⟨", "rangle": "⟩", "lceil": "⌈", "rceil": "⌉",
    "lfloor": "⌊", "rfloor": "⌋", "|": "‖", "Vert": "‖",
    "prime": "′", "backslash": "\\\\",
    "ldots": "…", "cdots": "⋯", "vdots": "⋮", "ddots": "⋱",
    "therefore": "∴", "because": "∵", "qed": "∎",
    "bigcup": "⋃", "bigcap": "⋂", "bigoplus": "⨁", "bigotimes": "⨂",
    "coprod": "∐", "bigvee": "⋁", "bigwedge": "⋀",
    "mathbb{R}": "ℝ", "mathbb{N}": "ℕ", "mathbb{Z}": "ℤ",
    "mathbb{Q}": "ℚ", "mathbb{C}": "ℂ", "mathbb{P}": "ℙ",
    "mathbb{E}": "𝔼", "mathbb{F}": "𝔽", "mathbb{H}": "ℍ",
    "mathcal{L}": "ℒ", "mathcal{F}": "ℱ", "mathcal{H}": "ℋ",
    "mathcal{O}": "𝒪", "mathcal{N}": "𝒩", "mathcal{P}": "𝒫",
    "mathcal{B}": "ℬ", "mathcal{E}": "ℰ", "mathcal{M}": "ℳ",
    "mathfrak{g}": "𝔤", "imath": "ı", "jmath": "ȷ",
    "checkmark": "✓", "S": "§", "P": "¶", "copyright": "©",
    "degree": "°", "textdegree": "°", "textmu": "µ",
}
try:
    SYMBOLS.update(_EXTRA_SYMBOLS)
except NameError:
    pass

_BRACED_SYMBOLS = {k: v for k, v in _EXTRA_SYMBOLS.items() if "{" in k}
