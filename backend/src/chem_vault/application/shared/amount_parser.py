"""Parse human-entered amount strings into (value, unit) tuples.

Handles variations like:
- "2mg", "2 mg", "2.5mg" -> (2.0/2.5, "mg")
- "5 grams", "5g" -> (5.0, "g")
- "0.5 mL", "0.5ml" -> (0.5, "mL")
- "100 umol", "100 umol" -> (100.0, "umol")
"""

from __future__ import annotations

import re

UNIT_ALIASES: dict[str, str] = {
    "mg": "mg",
    "milligram": "mg",
    "milligrams": "mg",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "ml": "mL",
    "milliliter": "mL",
    "milliliters": "mL",
    "millilitre": "mL",
    "l": "L",
    "liter": "L",
    "liters": "L",
    "litre": "L",
    "umol": "umol",
    "\u00b5mol": "umol",
    "micromol": "umol",
    "micromole": "umol",
}

_AMOUNT_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([a-zA-Z\u00b5\u03bc]+)\s*$")


def parse_amount(raw: str) -> tuple[float, str] | None:
    """Parse a human-entered amount string. Returns (value, canonical_unit) or None."""
    raw = raw.strip()

    # Try pattern: number + unit (possibly no space)
    m = _AMOUNT_RE.match(raw)
    if m:
        value = float(m.group(1))
        unit_raw = m.group(2).lower().rstrip("s")  # normalize plural
        # Check aliases
        canonical = UNIT_ALIASES.get(unit_raw) or UNIT_ALIASES.get(m.group(2).lower())
        if canonical:
            return (value, canonical)
        # If not in aliases but looks like a known unit pattern
        if unit_raw in ("mg", "g", "kg", "ml", "l", "umol"):
            return (value, UNIT_ALIASES.get(unit_raw, unit_raw))

    # Try split by space: "2 mg"
    parts = raw.split()
    if len(parts) == 2:
        try:
            value = float(parts[0])
            unit_raw = parts[1].lower().rstrip("s")
            canonical = UNIT_ALIASES.get(unit_raw) or UNIT_ALIASES.get(parts[1].lower())
            if canonical:
                return (value, canonical)
        except ValueError:
            pass

    return None
