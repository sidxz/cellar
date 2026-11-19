"""The precedence table for a reported intercept, shared by the domain function's test,
the Python readers' tests and the SQL mirror's integration test.

The class wins at both ends (inactive reads "> highest dose", active at all doses "< lowest
dose"); otherwise the stored qualifier decides; an intercept stored before qualifiers
(``qualifier=None``) reads by the old rules: at the bound or above the doses "> highest", below
them "< lowest", else the value.
"""

from __future__ import annotations

from dataclasses import dataclass

LO, HI = 0.01, 100.0  # the tested doses
IN, ABOVE, BELOW = 1.0, 500.0, 0.001  # a value inside, above and below them


@dataclass(frozen=True)
class Case:
    curve_class: str | None
    qualifier: str | None  # None: stored before qualifiers
    value: float | None  # None: no value (an "nd" intercept)
    expected: tuple[float | None, str]  # (value, ValueQualifier value)
    at_bound: bool = False
    doses: tuple[float, float] | None = (LO, HI)  # None: no tested dose recorded

    @property
    def id(self) -> str:
        rng = "" if self.doses else "-no-doses"
        bound = "-at-bound" if self.at_bound else ""
        return f"{self.curve_class}-{self.qualifier or 'legacy'}-{self.value}{bound}{rng}"


_GT, _LT, _EQ, _ND = (HI, ">"), (LO, "<"), "=", (None, "nd")

CASES: list[Case] = [
    # The class wins at both ends, whatever the stored qualifier or value.
    *(
        Case(cls, q, v, expected)
        for cls, expected in (("inactive", _GT), ("active_all_doses", _LT))
        for q in ("<", ">", "=", "nd", None)
        for v in (IN, ABOVE, BELOW)
    ),
    Case("inactive", "nd", None, _GT),
    Case("active_all_doses", "nd", None, _LT),
    # Any other class reads the stored qualifier.
    *(
        Case(cls, q, v, expected)
        for cls in ("full", "partial", "bell_shaped", None)
        for q, expected in (("<", _LT), (">", _GT))
        for v in (IN, ABOVE, BELOW)
    ),
    *(Case(cls, "=", IN, (IN, _EQ)) for cls in ("full", "partial", None)),
    *(Case(cls, "nd", v, _ND) for cls in ("full", "partial") for v in (IN, None)),
    Case("full", "=", None, _ND),  # no value to report
    # Stored before qualifiers: today's rules.
    Case("full", None, IN, (IN, _EQ)),
    Case("full", None, ABOVE, _GT),
    Case("full", None, BELOW, _LT),
    Case("full", None, IN, _GT, at_bound=True),
    Case("full", None, None, _GT, at_bound=True),
    Case("partial", None, IN, (IN, _EQ)),
    Case("full", None, None, _ND),
    # No tested dose to quote a bound at: n.d.; a value still reads.
    Case("inactive", None, IN, _ND, doses=None),
    Case("active_all_doses", "<", IN, _ND, doses=None),
    Case("full", "<", IN, _ND, doses=None),
    Case("full", ">", IN, _ND, doses=None),
    Case("full", "=", IN, (IN, _EQ), doses=None),
    Case("full", None, ABOVE, (ABOVE, _EQ), doses=None),
]
