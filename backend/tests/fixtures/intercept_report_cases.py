"""The precedence table for a reported intercept, shared by the domain function's test,
the Python readers' tests and the SQL mirror's integration test.

The class wins at both ends (inactive reads "> highest dose" on every intercept, active at
all doses "< lowest dose" on the primary only); otherwise the stored qualifier decides; an
intercept stored before qualifiers (``qualifier=None``) reads by the old rules: at the bound
or above the doses "> highest", below them "< lowest", else the value. A keyed intercept the
curve does not have (a key added after its fit) is n.d., whatever the class.
"""

from __future__ import annotations

from dataclasses import dataclass

LO, HI = 0.01, 100.0  # the tested doses
IN, ABOVE, BELOW = 1.0, 500.0, 0.001  # a value inside, above and below them

EC50 = {"kind": "ec", "level": 50.0, "basis": "relative_percent", "label": None}
EC90 = {**EC50, "level": 90.0}
# The primary in front of a secondary case's intercept: censored below the doses, as on a
# curve active at all doses.
_PRIMARY = {"spec": EC50, "value": LO, "at_bound": False, "qualifier": "<"}


@dataclass(frozen=True)
class Case:
    curve_class: str | None
    qualifier: str | None  # None: stored before qualifiers
    value: float | None  # None: no value (an "nd" intercept)
    expected: tuple[float | None, str]  # (value, ValueQualifier value)
    at_bound: bool = False
    doses: tuple[float, float] | None = (LO, HI)  # None: no tested dose recorded
    primary: bool = True  # False: the curve's EC90 behind its EC50 primary
    stored: bool = True  # False: the curve has no EC90 (only a secondary case)

    @property
    def id(self) -> str:
        rng = "" if self.doses else "-no-doses"
        bound = "-at-bound" if self.at_bound else ""
        role = "" if self.primary else "-secondary" if self.stored else "-missing"
        return f"{self.curve_class}-{self.qualifier or 'legacy'}-{self.value}{bound}{rng}{role}"

    @property
    def key(self) -> tuple[str, float]:
        """(kind, level) of the intercept the case reads."""
        spec = EC50 if self.primary else EC90
        return spec["kind"], spec["level"]

    def intercept_values(self) -> list[dict]:
        """The curve's stored ``intercept_values`` JSON."""
        iv: dict = {"spec": EC50 if self.primary else EC90, "value": self.value}
        iv["at_bound"] = self.at_bound
        if self.qualifier is not None:
            iv["qualifier"] = self.qualifier
        if self.primary:
            return [iv]
        return [_PRIMARY, iv] if self.stored else [_PRIMARY]


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
    # A secondary intercept: "active at all doses" speaks for the primary only, so the
    # EC90 behind it reads its own qualifier (CDD: "not calculable" for an in-band EC90);
    # inactive still reads "> highest dose" on every intercept.
    Case("active_all_doses", ">", IN, _GT, primary=False),
    Case("active_all_doses", "nd", None, _ND, primary=False),
    Case("active_all_doses", "=", IN, (IN, _EQ), primary=False),
    Case("active_all_doses", "<", IN, _LT, primary=False),
    # Set by hand on a curve fitted before qualifiers: the secondary reads today's rules.
    Case("active_all_doses", None, IN, (IN, _EQ), primary=False),
    Case("active_all_doses", None, ABOVE, _GT, primary=False),
    Case("active_all_doses", None, IN, _GT, at_bound=True, primary=False),
    Case("inactive", "=", IN, _GT, primary=False),
    Case("inactive", "nd", None, _GT, primary=False),
    Case("full", "=", IN, (IN, _EQ), primary=False),
    # A keyed intercept the curve does not have reads n.d. before any class rule.
    *(
        Case(cls, None, None, _ND, primary=False, stored=False)
        for cls in ("active_all_doses", "inactive", "full", None)
    ),
]
