"""Bulk entry refuses derived (calculated or temperature-window) readouts."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cellar.application.screening.bulk_create_readout_data import (
    BulkCreateReadoutData,
    BulkCreateReadoutDataCommand,
    ReadoutDataItem,
)
from cellar.domain.screening_assay.enums import ReadoutDataType
from cellar.domain.screening_assay.melt_window import MeltMeasure, MeltReadoutConfig
from cellar.domain.screening_assay.protocol import ReadoutDefinition


async def test_bulk_entry_refuses_melt_readout():
    run_id = uuid.uuid4()
    melt = ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name="Tm (Main)",
        data_type=ReadoutDataType.NUMERIC,
        unit="°C",
        melt_config=MeltReadoutConfig("Main", MeltMeasure.TM, "ratio", 50.0, 85.0),
    )
    run_repo, protocol_repo = AsyncMock(), AsyncMock()
    run_repo.find_by_id_in_workspace.return_value = SimpleNamespace(
        wells=[], protocol_id=melt.protocol_id
    )
    protocol_repo.find_by_id_in_workspace.return_value = SimpleNamespace(
        readout_definitions=[melt]
    )
    repo, uow = AsyncMock(), AsyncMock()
    uow.commit.return_value = []
    uc = BulkCreateReadoutData(
        uow, repo, AsyncMock(), AsyncMock(), run_repo=run_repo, protocol_repo=protocol_repo
    )
    common = dict(run_id=run_id, molecule_id=uuid.uuid4(), value_numeric=60.0)
    items = [
        ReadoutDataItem(readout_definition_id=melt.id, **common),
        ReadoutDataItem(readout_definition_name=melt.name, **common),
    ]
    result = await uc(
        BulkCreateReadoutDataCommand(workspace_id=uuid.uuid4(), items=items),
        auth=None,
        require_batch=False,
    )
    outcome = result.unwrap()
    assert (outcome.success_count, outcome.error_count) == (0, 2)
    assert all(melt.name in e["error"] for e in outcome.errors)
    repo.save_bulk.assert_not_called()


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
