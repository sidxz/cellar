"""GetVisualizationDataset / GetRunRowCounts — source resolution, row cap, scoping."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from returns.result import Failure, Success

from cellar.application.visualization.dataset_reader import ReadoutDefInfo, RunInfo, WellValueRow
from cellar.application.visualization.get_dataset import (
    MAX_DATASET_ROWS,
    GetVisualizationDataset,
    GetVisualizationDatasetQuery,
    ProtocolSource,
    RunSource,
)
from cellar.application.visualization.get_run_row_counts import (
    GetRunRowCounts,
    GetRunRowCountsQuery,
)
from cellar.domain.shared.errors import NotFoundError, ValidationError
from tests.fakes.fake_auth import FakeAuth

pytestmark = pytest.mark.asyncio

WS = uuid.uuid4()
P = uuid.uuid4()
RD = uuid.uuid4()


def _run(rid: uuid.UUID) -> RunInfo:
    return RunInfo(
        id=rid,
        protocol_id=P,
        run_date=date(2026, 11, 1),
        operator_id=uuid.uuid4(),
        status="approved",
        conditions=None,
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


def _value(run_id: uuid.UUID) -> WellValueRow:
    return WellValueRow(
        run_id=run_id,
        well_id=uuid.uuid4(),
        plate_id=uuid.uuid4(),
        plate_number=1,
        plate_barcode=None,
        plate_format="384",
        holder_rows=None,
        holder_columns=None,
        well_row="A",
        well_column=1,
        well_type="sample",
        dose=None,
        well_label=None,
        molecule_id=uuid.uuid4(),
        registration_number="CEL-1",
        smiles="C",
        batch_id=None,
        batch_number=None,
        readout_definition_id=RD,
        normalization_applied=None,
        value_numeric=1.0,
        value_qualifier=None,
        value_text=None,
        is_outlier=False,
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


class FakeReader:
    def __init__(self, runs: list[RunInfo], counts: dict[uuid.UUID, int]) -> None:
        self.runs = runs
        self.counts = counts
        self.fetched: list[uuid.UUID] | None = None

    async def runs_for_protocol(self, workspace_id, protocol_id):
        return self.runs if (workspace_id, protocol_id) == (WS, P) else None

    async def runs_by_ids(self, workspace_id, run_ids):
        return [r for r in self.runs if r.id in run_ids] if workspace_id == WS else []

    async def readout_definitions(self, workspace_id, protocol_ids):
        return [
            ReadoutDefInfo(
                id=RD,
                protocol_id=P,
                name="Signal",
                data_type="numeric",
                unit=None,
                display_order=0,
            )
        ]

    async def count_wells_rows(self, workspace_id, run_ids):
        return {r: self.counts[r] for r in run_ids if r in self.counts}

    async def fetch_well_values(self, workspace_id, run_ids):
        self.fetched = list(run_ids)
        return [_value(r) for r in run_ids]


A, B, FOREIGN = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _reader(count_a: int = 1, count_b: int = 1) -> FakeReader:
    return FakeReader([_run(A), _run(B)], {A: count_a, B: count_b})


async def test_protocol_source_loads_every_run():
    reader = _reader()
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P), level="wells"
    )
    result = await GetVisualizationDataset(reader)(q, auth=FakeAuth(workspace_id=WS))
    assert isinstance(result, Success)
    assert set(reader.fetched or []) == {A, B}
    assert len(result.unwrap().row_ids) == 2


async def test_protocol_source_with_a_run_subset():
    reader = _reader()
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P, run_ids=(B,)), level="wells"
    )
    result = await GetVisualizationDataset(reader)(q, auth=FakeAuth(workspace_id=WS))
    assert isinstance(result, Success)
    assert reader.fetched == [B]


async def test_run_source():
    reader = _reader()
    q = GetVisualizationDatasetQuery(workspace_id=WS, source=RunSource(run_id=A), level="wells")
    result = await GetVisualizationDataset(reader)(q, auth=FakeAuth(workspace_id=WS))
    assert isinstance(result, Success)
    assert reader.fetched == [A]


async def test_run_not_in_protocol_is_not_found():
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P, run_ids=(A, FOREIGN)), level="wells"
    )
    result = await GetVisualizationDataset(_reader())(q, auth=FakeAuth(workspace_id=WS))
    assert isinstance(result, Failure) and isinstance(result.failure(), NotFoundError)


async def test_unknown_protocol_and_unknown_run_are_not_found():
    uc = GetVisualizationDataset(_reader())
    for source in (ProtocolSource(protocol_id=uuid.uuid4()), RunSource(run_id=FOREIGN)):
        q = GetVisualizationDatasetQuery(workspace_id=WS, source=source, level="wells")
        result = await uc(q, auth=FakeAuth(workspace_id=WS))
        assert isinstance(result, Failure) and isinstance(result.failure(), NotFoundError)


async def test_over_the_row_cap_names_both_numbers():
    reader = _reader(count_a=MAX_DATASET_ROWS, count_b=1)
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P), level="wells"
    )
    result = await GetVisualizationDataset(reader)(q, auth=FakeAuth(workspace_id=WS))
    assert isinstance(result, Failure)
    err = result.failure()
    assert isinstance(err, ValidationError)
    assert f"{MAX_DATASET_ROWS + 1:,}" in str(err) and f"{MAX_DATASET_ROWS:,}" in str(err)
    assert reader.fetched is None  # refused before loading anything


async def test_other_workspace_caller_is_refused():
    q = GetVisualizationDatasetQuery(workspace_id=WS, source=RunSource(run_id=A), level="wells")
    with pytest.raises(NotFoundError):
        await GetVisualizationDataset(_reader())(q, auth=FakeAuth(workspace_id=uuid.uuid4()))


async def test_run_row_counts_fill_zero_for_runs_without_data():
    reader = FakeReader([_run(A), _run(B)], {A: 7})
    q = GetRunRowCountsQuery(workspace_id=WS, protocol_id=P)
    result = await GetRunRowCounts(reader)(q, auth=FakeAuth(workspace_id=WS))
    assert result.unwrap() == {A: 7, B: 0}


async def test_run_row_counts_unknown_protocol():
    q = GetRunRowCountsQuery(workspace_id=WS, protocol_id=uuid.uuid4())
    result = await GetRunRowCounts(_reader())(q, auth=FakeAuth(workspace_id=WS))
    assert isinstance(result, Failure) and isinstance(result.failure(), NotFoundError)
