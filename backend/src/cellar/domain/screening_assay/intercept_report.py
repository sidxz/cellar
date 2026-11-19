"""One curve intercept as every reader reports it: a value, or a bound at the tested doses.

The SQL readers mirror this rule (``reported_curve_value`` in the persistence layer), and the
frontend's ``formatInterceptDisplay`` applies it to one curve on screen.
"""

from __future__ import annotations

import math

from cellar.domain.screening_assay.enums import CurveClass
from cellar.domain.shared.aggregation_types import ValueQualifier


def report_intercept(
    curve_class: str | None,
    qualifier: str | None,
    value: float | None,
    low_dose: float | None,
    high_dose: float | None,
    *,
    at_bound: bool = False,
) -> tuple[float | None, ValueQualifier]:
    """(value, qualifier) of one intercept of a curve tested from ``low_dose`` to
    ``high_dose``.

    The class wins at both ends, set by the fitter or by a scientist: ``inactive`` reads
    "> highest dose", ``active_all_doses`` "< lowest dose". Any other class reads the
    stored qualifier: ``>`` / ``<`` the bound dose, ``nd`` no value, ``=`` the value. An
    intercept stored before qualifiers (``qualifier`` None) reads by the old rules: at the
    bound or above the doses "> highest", below them "< lowest", else the value. A bound
    with no dose to quote it at, or no value, is ``nd``.
    """
    if curve_class == CurveClass.INACTIVE:
        return _bound(high_dose, ValueQualifier.GT)
    if curve_class == CurveClass.ACTIVE_ALL_DOSES:
        return _bound(low_dose, ValueQualifier.LT)
    if qualifier == ValueQualifier.GT:
        return _bound(high_dose, ValueQualifier.GT)
    if qualifier == ValueQualifier.LT:
        return _bound(low_dose, ValueQualifier.LT)
    if qualifier == ValueQualifier.ND:
        return None, ValueQualifier.ND
    legacy = qualifier is None  # stored before qualifiers
    if legacy and at_bound:
        return _bound(high_dose, ValueQualifier.GT)
    number = float(value) if isinstance(value, int | float) and math.isfinite(value) else None
    if number is None:
        return None, ValueQualifier.ND
    if legacy and high_dose is not None and number > high_dose:
        return high_dose, ValueQualifier.GT
    if legacy and low_dose is not None and number < low_dose:
        return low_dose, ValueQualifier.LT
    return number, ValueQualifier.EQ


def _bound(dose: float | None, qualifier: ValueQualifier) -> tuple[float | None, ValueQualifier]:
    return (dose, qualifier) if dose is not None else (None, ValueQualifier.ND)
