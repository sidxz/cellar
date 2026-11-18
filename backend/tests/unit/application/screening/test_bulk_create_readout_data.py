"""Bulk entry refuses derived (calculated or temperature-window) readouts."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from cellar.application.screening.bulk_create_readout_data import (
    BulkCreateReadoutData,
    BulkCreateReadoutDataCommand,
    ReadoutDataItem,
)
from cellar.domain.screening_assay.enums import ReadoutDataType
from cellar.domain.screening_assay.melt_window import MeltMeasure, MeltReadoutConfig
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.shared.errors import ValidationError


async def test_bulk_entry_refuses_melt_readout():
    run_id = uuid.uuid4()
    melt = ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name="Tm (Main)",
        data_type=ReadoutDataType.NUMERIC,
        unit="°C",
        melt_config=MeltReadoutConfig("Main", MeltMeasure.TM, "ratio", 50.0, 85.0),
    )
    uc = BulkCreateReadoutData(AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock())
    cache = {run_id: {"definitions": [melt]}}
    for item in (
        ReadoutDataItem(run_id=run_id, readout_definition_id=melt.id),
        ReadoutDataItem(run_id=run_id, readout_definition_name=melt.name),
    ):
        result = await uc._resolve_readout_definition_id(uuid.uuid4(), item, 0, cache)
        assert isinstance(result.failure(), ValidationError)
        assert "calculated or derived" in str(result.failure())


async def test_well_rows_never_get_replicate_count():
    run_id, rdef = uuid.uuid4(), uuid.uuid4()
    repo = AsyncMock()
    uow = AsyncMock()
    uow.commit.return_value = []
    uc = BulkCreateReadoutData(uow, repo, AsyncMock(), AsyncMock())
    common = dict(
        run_id=run_id,
        molecule_id=uuid.uuid4(),
        readout_definition_id=rdef,
        value_numeric=1.0,
        replicate_count=3,
    )
    items = [
        ReadoutDataItem(well_id=uuid.uuid4(), batch_id=uuid.uuid4(), **common),
        ReadoutDataItem(well_id=None, **common),
    ]
    result = await uc(
        BulkCreateReadoutDataCommand(workspace_id=uuid.uuid4(), items=items),
        auth=None,
        require_batch=False,
    )
    saved = repo.save_bulk.call_args.args[0]
    assert [r.replicate_count for r in saved] == [None, 3], result
