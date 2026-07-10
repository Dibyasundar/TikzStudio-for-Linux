"""Approximate LaTeX math -> Unicode for WYSIWYG node display.

The canvas cannot run TeX per keystroke, so node text is converted to a
Unicode approximation (Greek letters, operators, super/subscripts,
fractions).  The compiled PDF preview remains the exact rendering.
"""

import re

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
