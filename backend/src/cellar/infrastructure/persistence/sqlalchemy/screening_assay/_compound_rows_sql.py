"""SQL shared by every compound-level query: which readout rows are a compound's
results, and the doses a curve's reported potency is censored at."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, Float, FromClause, case, cast, column, exists, func
from sqlalchemy import literal_column as lit
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased

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
