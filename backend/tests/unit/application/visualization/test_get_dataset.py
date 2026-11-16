"""GetVisualizationDataset / GetRunRowCounts — source resolution, row cap, scoping."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, date, datetime

import pytest
from returns.result import Failure, Success

from cellar.application.screening.get_protocol_activity import VALID_STATUSES
from cellar.application.screening.protocol_activity_reader import (
    ActivityAggregates,
    AggregateScope,
    NumericReadoutRow,
)
from cellar.application.visualization.dataset_reader import (
    CompoundInfo,
    ReadoutDefInfo,
    RunInfo,
    WellValueRow,
)
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

    async def fetch_curves(self, workspace_id, run_ids):
        self.curves_for = list(run_ids)
        return []

    async def compound_info(self, workspace_id, molecule_ids):
        self.molecules_asked = set(molecule_ids)
        return {m: _info(f"CEL-{i}") for i, m in enumerate(sorted(molecule_ids))}

    async def batch_numbers(self, workspace_id, batch_ids):
        self.batches_asked = set(batch_ids)
        return {b: "B-1" for b in batch_ids}


def _info(reg: str) -> CompoundInfo:
    return CompoundInfo(reg, "C", 300.0, None, None, None, None, None, None)


class FakeActivity:
    """Aggregates: one numeric row per molecule given, in batch BATCH."""

    def __init__(self, molecules: tuple[uuid.UUID, ...] = ()) -> None:
        self.molecules = molecules
        self.calls: list[tuple[uuid.UUID, AggregateScope]] = []

    async def get_aggregates(self, workspace_id, protocol_id, scope):
        assert workspace_id == WS
        self.calls.append((protocol_id, scope))
        rows = [
            NumericReadoutRow(
                molecule_id=m,
                readout_name="Signal",
                best=1.0,
                mean=1.0,
                n=1,
                sd=None,
                readout_definition_id=RD,
                batch_id=BATCH if scope.grain != "compound" else None,
                run_id=A if scope.grain == "run" else None,
            )
            for m in self.molecules
        ]
        return ActivityAggregates(numeric_rows=rows, dr_agg_rows=[])


A, B, FOREIGN, BATCH = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _reader(count_a: int = 1, count_b: int = 1) -> FakeReader:
    return FakeReader([_run(A), _run(B)], {A: count_a, B: count_b})


async def test_protocol_source_loads_every_run():
    reader = _reader()
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P), level="wells"
    )
    result = await GetVisualizationDataset(reader, FakeActivity())(
        q, auth=FakeAuth(workspace_id=WS)
    )
    assert isinstance(result, Success)
    assert set(reader.fetched or []) == {A, B}
    assert len(result.unwrap().row_ids) == 2


async def test_protocol_source_with_a_run_subset():
    reader = _reader()
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P, run_ids=(B,)), level="wells"
    )
    result = await GetVisualizationDataset(reader, FakeActivity())(
        q, auth=FakeAuth(workspace_id=WS)
    )
    assert isinstance(result, Success)
    assert reader.fetched == [B]


async def test_repeated_run_ids_load_the_run_once():
    reader = _reader()
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P, run_ids=(B, A, B)), level="wells"
    )
    result = await GetVisualizationDataset(reader, FakeActivity())(
        q, auth=FakeAuth(workspace_id=WS)
    )
    assert reader.fetched == [B, A]
    assert len(result.unwrap().row_ids) == 2


async def test_dataset_is_built_off_the_event_loop_thread(monkeypatch):
    from cellar.application.visualization import get_dataset

    threads: list[int] = []
    real = get_dataset.build_wells_dataset

    def spy(*args):
        threads.append(threading.get_ident())
        return real(*args)

    monkeypatch.setattr(get_dataset, "build_wells_dataset", spy)
    q = GetVisualizationDatasetQuery(workspace_id=WS, source=RunSource(run_id=A), level="wells")
    await GetVisualizationDataset(_reader(), FakeActivity())(q, auth=FakeAuth(workspace_id=WS))
    assert threads and threads[0] != threading.get_ident()


async def test_run_source():
    reader = _reader()
    q = GetVisualizationDatasetQuery(workspace_id=WS, source=RunSource(run_id=A), level="wells")
    result = await GetVisualizationDataset(reader, FakeActivity())(
        q, auth=FakeAuth(workspace_id=WS)
    )
    assert isinstance(result, Success)
    assert reader.fetched == [A]


async def test_run_not_in_protocol_is_not_found():
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P, run_ids=(A, FOREIGN)), level="wells"
    )
    result = await GetVisualizationDataset(_reader(), FakeActivity())(
        q, auth=FakeAuth(workspace_id=WS)
    )
    assert isinstance(result, Failure) and isinstance(result.failure(), NotFoundError)


async def test_unknown_protocol_and_unknown_run_are_not_found():
    uc = GetVisualizationDataset(_reader(), FakeActivity())
    for source in (ProtocolSource(protocol_id=uuid.uuid4()), RunSource(run_id=FOREIGN)):
        q = GetVisualizationDatasetQuery(workspace_id=WS, source=source, level="wells")
        result = await uc(q, auth=FakeAuth(workspace_id=WS))
        assert isinstance(result, Failure) and isinstance(result.failure(), NotFoundError)


async def test_over_the_row_cap_names_both_numbers():
    reader = _reader(count_a=MAX_DATASET_ROWS, count_b=1)
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P), level="wells"
    )
    result = await GetVisualizationDataset(reader, FakeActivity())(
        q, auth=FakeAuth(workspace_id=WS)
    )
    assert isinstance(result, Failure)
    err = result.failure()
    assert isinstance(err, ValidationError)
    assert f"{MAX_DATASET_ROWS + 1:,}" in str(err) and f"{MAX_DATASET_ROWS:,}" in str(err)
    assert reader.fetched is None  # refused before loading anything


async def test_other_workspace_caller_is_refused():
    q = GetVisualizationDatasetQuery(workspace_id=WS, source=RunSource(run_id=A), level="wells")
    with pytest.raises(NotFoundError):
        await GetVisualizationDataset(_reader(), FakeActivity())(
            q, auth=FakeAuth(workspace_id=uuid.uuid4())
        )


@pytest.mark.parametrize(
    ("level", "scope"),
    [
        ("runs", AggregateScope(statuses=None, run_ids=(A, B), grain="run")),
        ("batches", AggregateScope(VALID_STATUSES, (A, B), "batch", by_conditions=True)),
        ("compounds", AggregateScope(VALID_STATUSES, (A, B), "compound", by_conditions=True)),
    ],
)
async def test_each_aggregated_level_reads_its_scope(level, scope):
    reader, mol = _reader(), uuid.uuid4()
    activity = FakeActivity((mol,))
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P), level=level
    )
    result = await GetVisualizationDataset(reader, activity)(q, auth=FakeAuth(workspace_id=WS))
    ds = result.unwrap()
    assert activity.calls == [(P, scope)]
    assert ds.level == level and ds.values["compound"] == ["CEL-0"]
    assert reader.molecules_asked == {mol}
    assert getattr(reader, "curves_for", None) == ([A, B] if level == "runs" else None)
    if level != "compounds":
        assert reader.batches_asked == {BATCH} and ds.values["batch"] == ["B-1"]
    assert reader.fetched is None  # no well values at an aggregated level


async def test_a_run_source_aggregates_that_run_of_its_protocol():
    activity = FakeActivity((uuid.uuid4(),))
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=RunSource(run_id=B), level="compounds"
    )
    await GetVisualizationDataset(_reader(), activity)(q, auth=FakeAuth(workspace_id=WS))
    [(protocol_id, scope)] = activity.calls
    assert (protocol_id, scope.run_ids) == (P, (B,))


async def test_a_protocol_without_runs_gives_an_empty_aggregated_dataset():
    activity = FakeActivity()
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P), level="batches"
    )
    result = await GetVisualizationDataset(FakeReader([], {}), activity)(
        q, auth=FakeAuth(workspace_id=WS)
    )
    assert result.unwrap().row_ids == []
    assert activity.calls == [(P, AggregateScope(VALID_STATUSES, (), "batch", by_conditions=True))]


async def test_aggregated_row_cap_counts_the_built_rows(monkeypatch):
    from cellar.application.visualization import get_dataset

    monkeypatch.setattr(get_dataset, "MAX_DATASET_ROWS", 1)
    activity = FakeActivity((uuid.uuid4(), uuid.uuid4()))
    q = GetVisualizationDatasetQuery(
        workspace_id=WS, source=ProtocolSource(protocol_id=P), level="compounds"
    )
    result = await GetVisualizationDataset(_reader(), activity)(q, auth=FakeAuth(workspace_id=WS))
    assert isinstance(result, Failure) and isinstance(result.failure(), ValidationError)
    assert "2 rows" in str(result.failure()) and "limit is 1" in str(result.failure())


async def test_wells_carry_compound_descriptors():
    q = GetVisualizationDatasetQuery(workspace_id=WS, source=RunSource(run_id=A), level="wells")
    result = await GetVisualizationDataset(_reader(), FakeActivity())(
        q, auth=FakeAuth(workspace_id=WS)
    )
    assert result.unwrap().values["molecular_weight"] == [300.0]


async def test_run_row_counts_fill_zero_for_runs_without_data():
    reader = FakeReader([_run(A), _run(B)], {A: 7})
    q = GetRunRowCountsQuery(workspace_id=WS, protocol_id=P)
    result = await GetRunRowCounts(reader)(q, auth=FakeAuth(workspace_id=WS))
    assert result.unwrap() == {A: 7, B: 0}


async def test_run_row_counts_unknown_protocol():
    q = GetRunRowCountsQuery(workspace_id=WS, protocol_id=uuid.uuid4())
    result = await GetRunRowCounts(_reader())(q, auth=FakeAuth(workspace_id=WS))
    assert isinstance(result, Failure) and isinstance(result.failure(), NotFoundError)
