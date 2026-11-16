"""Which readout rows are a compound's results, shared by every compound-level query."""

from __future__ import annotations

from sqlalchemy import ColumnElement, exists
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
