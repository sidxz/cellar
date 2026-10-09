"""Units on readouts, conditions and form templates: one spelling per unit, by rule.

``canonical_unit`` rewrites spelling variants of the same unit (uM, μM, umol/L → µM) and
leaves everything else exactly as typed, so any unit normalizes consistently without a list
and nothing ever converts between different units.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MICRO = "µ"  # micro sign: the canonical spelling
_MICRO_PREFIXED = re.compile(r"^(?:u|μ|µ|mc)(mol|M|g|L|l|m|s)$")
_LITRE = re.compile(r"^([pnµmdck]?)l$")
_WORDS = {
    "hr": "h",
    "hrs": "h",
    "hour": "h",
    "hours": "h",
    "mins": "min",
    "minute": "min",
    "minutes": "min",
    "sec": "s",
    "secs": "s",
    "second": "s",
    "seconds": "s",
    "day": "d",
    "days": "d",
    "percent": "%",
    "pct": "%",
}
_DEGREES = re.compile(r"^(?:deg\s*C|degC|°c)$", re.IGNORECASE)
# '/' and '·' separate tokens and are kept; '*' is a product sign, and so is a '.' between
# letters, except inside a dotted abbreviation ('a.u.', 'O.D.': single letters, each dotted).
_SEPARATOR = re.compile(
    r"""(
        / | · | \*
        | (?<=[A-Za-zµ%])\.(?=[A-Za-zµ])            # a '.' between letters,
          (?:(?<=[A-Za-zµ%]{2}\.)|(?![A-Za-zµ]\.))  # unless both sides are lone dotted letters
    )""",
    re.VERBOSE,
)
# An ASCII power-of-ten factor before a unit ('10-6', '10^-6', 'x10-6', '1e-6') is written ×10⁻⁶.
_POWER_OF_TEN = re.compile(
    r"^(?:[x×*]\s*)?(?:10\s*\^\s*|10(?=-)|1e)([-+]?\d+)\s*(?=[^\W\d_])", re.IGNORECASE
)
_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹", "+")
_MOLAR = re.compile(r"(?<![A-Za-z])([pnµm]?)mol/L(?![A-Za-z])")


def _token(token: str) -> str:
    t = " ".join(token.split())
    if t.lower() in _WORDS:
        return _WORDS[t.lower()]
    if _DEGREES.match(t):
        return "°C"
    if t == "Kg":
        return "kg"
    # A lone lowercase 'um' is µM in an assay but µm as a length: ambiguous, so left as typed.
    m = _MICRO_PREFIXED.match(t) if t != "um" else None
    if m:
        t = MICRO + m.group(1)
    m = _LITRE.match(t)
    if m:
        t = m.group(1) + "L"
    return t


def canonical_unit(text: str | None) -> str | None:
    if text is None or not text.strip():
        return None
    text = text.strip()
    factor = ""
    if m := _POWER_OF_TEN.match(text):
        factor = f"×10{m.group(1).translate(_SUPERSCRIPT)} "
        text = text[m.end() :]
    parts = _SEPARATOR.split(text)
    out: list[str] = []
    for part in parts:
        if part in ("*", "."):
            out.append("·")
        elif part in ("/", "·"):
            out.append(part)
        else:
            out.append(_token(part))
    return factor + _MOLAR.sub(lambda m: m.group(1) + "M", "".join(out))


@dataclass(frozen=True)
class UnitSuggestion:
    unit: str
    group: str


def _group(group: str, *units: str) -> tuple[UnitSuggestion, ...]:
    return tuple(UnitSuggestion(u, group) for u in units)


COMMON_UNITS: tuple[UnitSuggestion, ...] = (
    *_group("Concentration", f"{MICRO}M", "nM", "mM", "pM", "M"),
    *_group("Mass concentration", f"{MICRO}g/mL", "ng/mL", "mg/mL"),
    *_group("Dose", "mg/kg"),
    *_group("Percent and ratio", "%", "fold", "fraction"),
    *_group("Counts", "log10 CFU", "CFU/mL"),
    *_group("Time", "h", "min", "s", "d"),
    *_group("Clearance", f"{MICRO}L/min/mg", "mL/min/kg"),
    *_group("Permeability", "×10⁻⁶ cm/s"),
    *_group("Exposure", "ng·h/mL"),
    *_group("Signal", "RFU", "RLU", "AU", "mP", "OD600", "counts"),
    *_group("Temperature", "°C"),
    *_group("Mass", "Da"),
)
