"""SQL shared by every compound-level query: which readout rows are a compound's
results, and the doses a curve's reported potency is censored at."""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    ColumnElement,
    Float,
    FromClause,
    and_,
    case,
    cast,
    column,
    exists,
    false,
    func,
    literal,
    null,
    select,
)
from sqlalchemy import literal_column as lit
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased

from cellar.domain.screening_assay.enums import CurveClass
from cellar.domain.shared.enums import WellType
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    PlateModel,
    ReadoutDataModel,
    WellModel,
)

_well, _plate = aliased(WellModel), aliased(PlateModel)

# The row is one of its compound's results: well-less (a summary import) or on a sample
# well. Control, reference and blank wells are plate QC: their rows keep the compound
# (the Wells level names it) but never feed its numbers, campaign picks or exports. Only
# a well on a plate of the row's own run is read; a well_id pointing anywhere else reads
# as well-less, as the Wells level reads it.
COMPOUND_RESULT: ColumnElement[bool] = ~exists().where(
    _well.id == ReadoutDataModel.well_id,
    _plate.id == _well.plate_id,
    _plate.run_id == ReadoutDataModel.run_id,
    _well.well_type != WellType.SAMPLE.value,
)


def curve_doses(curve: Any) -> tuple[FromClause, ColumnElement[Any]]:
    """(points, dose): a FROM over the curve's ``raw_data`` points and each point's dose
    (NULL unless a number), read as ``run_aggregation._dose_range_from_raw`` reads them
    (``concentration``, else ``x``). Select ``min``/``max`` of it ``where dose > 0``."""
    raw = curve.raw_data
    pt = (
        func.jsonb_array_elements(case((func.jsonb_typeof(raw) == "array", raw)))
        .table_valued(column("value", JSONB))
        .alias("pt")
    )
    x = case(
        (pt.c.value.has_key("concentration"), pt.c.value["concentration"]), else_=pt.c.value["x"]
    )
    dose = case((func.jsonb_typeof(x) == "number", cast(x.op("#>>")(lit("'{}'")), Float)))
    return pt, dose


def primary_intercept(curve: Any) -> tuple[ColumnElement[Any], ...]:
    """(fitted_value, at_bound, qualifier) of the curve's primary intercept: the indexed
    ``fitted_value`` with ``intercept_values[0]``'s flag and stored qualifier (NULL when
    stored before qualifiers)."""
    first = curve.intercept_values[0]
    at_bound = func.coalesce(first["at_bound"] == lit("'true'::jsonb"), false())
    return curve.fitted_value, at_bound, first["qualifier"].astext


def _dose_bound(curve: Any, agg: Any) -> ColumnElement[Any]:
    pt, dose = curve_doses(curve)
    return select(agg(dose)).select_from(pt).where(dose > 0).scalar_subquery()


def reported_curve_value(
    curve: Any,
    value: Any,
    at_bound: Any,
    qualifier: Any,
    *,
    lo: Any = None,
    hi: Any = None,
) -> tuple[ColumnElement[Any], ColumnElement[Any]]:
    """(value, qualifier) of one curve intercept as every reader reports it, the SQL mirror
    of ``domain.screening_assay.intercept_report.report_intercept``: an inactive curve is
    ``>`` its top dose and one active at all doses ``<`` its lowest; otherwise the stored
    ``qualifier`` decides (``>`` / ``<`` the bound dose, ``nd`` no value); an intercept
    stored before qualifiers (``qualifier`` NULL) at the bound or above the doses is ``>``
    the top dose, below them ``<`` the lowest. An exact value has qualifier NULL; a NULL
    value is n.d. (nothing to report, or no dose to quote a bound at).

    ``lo`` / ``hi`` (the curve's lowest / highest positive dose) default to subqueries
    over its ``raw_data``; a caller that already has them (a lateral join) passes them in.
    """
    lo = _dose_bound(curve, func.min) if lo is None else lo
    hi = _dose_bound(curve, func.max) if hi is None else hi
    legacy = qualifier.is_(None)
    rules = [  # (when, value, qualifier), first match wins
        (curve.curve_class == CurveClass.INACTIVE.value, hi, ">"),
        (curve.curve_class == CurveClass.ACTIVE_ALL_DOSES.value, lo, "<"),
        (qualifier == ">", hi, ">"),
        (qualifier == "<", lo, "<"),
        (qualifier == "nd", null(), None),
        (and_(legacy, at_bound), hi, ">"),
        (and_(legacy, value > hi), hi, ">"),
        (and_(legacy, value < lo), lo, "<"),
    ]
    return (
        case(*((when, v) for when, v, _ in rules), else_=value),
        case(*((when, literal(q) if q else null()) for when, _, q in rules)),
    )
