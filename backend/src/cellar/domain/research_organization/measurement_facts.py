"""Facts recorded about a campaign measurement: the concentration it was taken at."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from cellar.domain.shared.units import MICRO, canonical_unit, comparable_magnitude

TEST_CONCENTRATION = "Test concentration"

_TEXT = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(\S*)\s*$")


@dataclass(frozen=True)
class Concentration:
    value: float
    unit: str

    def same_as(self, other: Concentration) -> bool:
        fa, a = comparable_magnitude(self.value, self.unit)
        fb, b = comparable_magnitude(other.value, other.unit)
        return fa == fb and math.isclose(a, b, rel_tol=1e-9)


def parse_concentration(raw: object, default_unit: str = f"{MICRO}M") -> Concentration | None:
    """A molar concentration from "10 µM" / "10 uM" / a bare number / {"value","unit"}.
    Anything else (including a lone lowercase "um", ambiguous with µm) is None."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, dict):
        value, unit = raw.get("value"), raw.get("unit")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
    elif isinstance(raw, (int, float)):
        value, unit = raw, default_unit
    elif isinstance(raw, str):
        m = _TEXT.match(raw)
        if not m:
            return None
        value, unit = float(m.group(1)), m.group(2) or default_unit
    else:
        return None
    unit = canonical_unit(unit if isinstance(unit, str) else None)
    if unit is None or not math.isfinite(value):
        return None
    if comparable_magnitude(1, unit)[0] != "molar":
        return None
    return Concentration(float(value), unit)
