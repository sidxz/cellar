"""Unit tests for ImportInstrumentFile."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date
from types import SimpleNamespace, TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.import_instrument_file import (
    COMPUTE_FAILED,
    ImportInstrumentFile,
    ImportInstrumentFileCommand,
    InstrumentLabelling,
    PositionLabelling,
    SeriesMapping,
)
from cellar.application.screening.instrument_export import (
    ExportChannel,
    ExportCurve,
    ExportPosition,
    HolderLayout,
    InstrumentExport,
    InstrumentReaders,
    ReportedValue,
)
from cellar.domain.attachment.enums import AttachableType
from cellar.domain.screening_assay.enums import HolderKind, ReadoutDataType, RunStatus
from cellar.domain.screening_assay.events import RunInstrumentFileImported
from cellar.domain.screening_assay.holder import position_label
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.screening_assay.run import Plate, Run
from cellar.domain.shared.enums import ConcentrationUnit, PlateFormat, WellType
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from tests.fakes.fake_auth import FakeAuth


class FakeUoW:
    """Returns the events of the aggregates it was given, like the real unit of work."""

    def __init__(self, tracked: list) -> None:
        self.tracked = tracked
        self.committed = False

    async def commit(self) -> list:
        self.committed = True
        return [e for a in self.tracked for e in a.collect_events()]

    async def rollback(self) -> None:  # pragma: no cover
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


CHANNELS = (
    ExportChannel("ratio", "Ratio", "°C", None, "Temperature"),
    ExportChannel("signal", "Signal", "°C", "a.u."),
)


def _reported(
    column: int,
    channel: str = "ratio",
    kind: str = "onset",
    value: float = 55.0,
    ordinal: int = 1,
) -> ReportedValue:
    return ReportedValue(
        row=1,
        column=column,
        channel=channel,
        kind=kind,
        ordinal=ordinal,
        label=f"{kind.title()} #{ordinal} for {channel.title()}",
        value=value,
        unit="°C",
    )


def _export(
    reported: tuple[ReportedValue, ...] | None = None, y: tuple[float, ...] = (1.0, 1.1, 1.2)
) -> InstrumentExport:
    columns = (1, 2, 3)
    return InstrumentExport(
        reader="stub",
        holder=HolderLayout(HolderKind.CASSETTE, 1, 3),
        positions=tuple(ExportPosition(1, c, f"sample {c}") for c in columns),
        channels=CHANNELS,
        curves=tuple(
            ExportCurve(1, c, ch.key, (20.0, 21.0, 22.0), y) for c in columns for ch in CHANNELS
        ),
        reported=tuple(_reported(c, value=50.0 + c) for c in columns)
        if reported is None
        else reported,
        settings={},
    )


class StubReader:
    id = "stub"
    label = "Stub format"
    hint = "Export format A"

    def __init__(self, export: InstrumentExport) -> None:
        self._export = export
        self.called = False

    def recognises(self, content: bytes, filename: str) -> bool:
        self.called = True
        return True

    def read(self, content: bytes, filename: str) -> InstrumentExport:
        return self._export


def _definition(
    name: str,
    unit: str | None = "°C",
    *,
    data_type: ReadoutDataType = ReadoutDataType.NUMERIC,
    calculated: bool = False,
) -> ReadoutDefinition:
    return ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name=name,
        data_type=data_type,
        unit=unit,
        is_calculated=calculated,
        calculation_formula="1" if calculated else None,
    )


class Harness:
    def __init__(self, *, export: InstrumentExport | None = None) -> None:
        self.auth = FakeAuth()
        self.ws = self.auth.workspace_id
        self.run = Run(
            workspace_id=self.ws,
            protocol_id=uuid.uuid4(),
            run_date=date(2026, 11, 12),
            operator=uuid.uuid4(),
            status=RunStatus.IN_PROGRESS,
        )
        self.tm1 = _definition("Onset #1 for Ratio")
        self.percent = _definition("Percent", "%")
        self.calculated = _definition("Derived", calculated=True)
        self.text = _definition("Comment", None, data_type=ReadoutDataType.TEXT)
        self.protocol = SimpleNamespace(
            id=self.run.protocol_id,
            dose_unit=ConcentrationUnit.UM,
            readout_definitions=[self.tm1, self.percent, self.calculated, self.text],
        )
        self.batch = SimpleNamespace(id=uuid.uuid4(), molecule_id=uuid.uuid4())
        self.batch2 = SimpleNamespace(id=uuid.uuid4(), molecule_id=uuid.uuid4())
        known = {b.id: b for b in (self.batch, self.batch2)}

        self.calls: list[str] = []
        self.uow = FakeUoW([self.run])
        self.run_repo = AsyncMock()
        self.run_repo.find_by_id_in_workspace = AsyncMock(return_value=self.run)
        self.run_repo.save = AsyncMock(side_effect=lambda run: self.calls.append("run"))
        self.protocol_repo = AsyncMock()
        self.protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=self.protocol)
        self.readout_repo = AsyncMock()
        self.readout_repo.has_wellless_rows = AsyncMock(return_value=False)
        self.readout_repo.save_bulk = AsyncMock(side_effect=lambda rows: self.calls.append("rd"))
        self.curve_repo = AsyncMock()
        self.curve_repo.save_bulk = AsyncMock(side_effect=lambda rows: self.calls.append("curve"))
        self.step_repo = AsyncMock()
        self.step_repo.save_bulk = AsyncMock(side_effect=lambda rows: self.calls.append("step"))
        self.batch_repo = AsyncMock()
        self.batch_repo.find_by_ids = AsyncMock(
            side_effect=lambda ws, ids: [known[i] for i in ids if i in known]
        )
        self.reader = StubReader(export or _export())
        self.attachment_id = uuid.uuid4()
        self.upload_attachment = AsyncMock(
            return_value=Success(SimpleNamespace(id=self.attachment_id))
        )
        self.attachment_repo = AsyncMock()
        self.attachment_repo.find_by_entity = AsyncMock(return_value=[])
        self.engine = AsyncMock()
        self.engine.compute_for_run = AsyncMock(return_value=Success(SimpleNamespace()))
        self.dispatcher = AsyncMock()
        self.uc = ImportInstrumentFile(
            uow=self.uow,
            run_repo=self.run_repo,
            protocol_repo=self.protocol_repo,
            readout_repo=self.readout_repo,
            curve_repo=self.curve_repo,
            step_repo=self.step_repo,
            batch_repo=self.batch_repo,
            readers=InstrumentReaders((self.reader,)),
            attachment_repo=self.attachment_repo,
            upload_attachment=self.upload_attachment,
            calculation_engine=self.engine,
            dispatcher=self.dispatcher,
        )
        self.positions = (
            PositionLabelling(
                row=1, column=1, label="protein alone", well_type=WellType.REFERENCE
            ),
            PositionLabelling(
                row=1, column=2, label="ABC-0000001", batch_id=self.batch.id, dose=10
            ),
            PositionLabelling(
                row=1, column=3, label="ABC-0000002", batch_id=self.batch2.id, dose=10
            ),
        )
        self.series = (SeriesMapping("ratio", "onset", 1, self.tm1.id),)

    def command(
        self,
        positions: tuple[PositionLabelling, ...] | None = None,
        series: tuple[SeriesMapping, ...] | None = None,
    ) -> ImportInstrumentFileCommand:
        return ImportInstrumentFileCommand(
            workspace_id=self.ws,
            run_id=self.run.id,
            filename="run.bin",
            content=b"x",
            labelling=InstrumentLabelling(
                positions=self.positions if positions is None else positions,
                series=self.series if series is None else series,
            ),
        )

    async def __call__(self, cmd: ImportInstrumentFileCommand | None = None, auth=None):
        return await self.uc(cmd or self.command(), auth=auth or self.auth)

    def assert_nothing_written(self) -> None:
        self.run_repo.save.assert_not_awaited()
        self.readout_repo.save_bulk.assert_not_awaited()
        self.curve_repo.save_bulk.assert_not_awaited()
        self.step_repo.save_bulk.assert_not_awaited()
        assert self.uow.committed is False
        assert self.run.plates == [] and self.run.wells == []
        self.dispatcher.dispatch_all.assert_not_awaited()
        self.upload_attachment.assert_not_awaited()


async def test_success_writes_holder_wells_readouts_curves_and_event():
    h = Harness()
    result = (await h()).unwrap()

    assert (result.reader, result.positions_created, result.curves_created) == ("stub", 3, 6)
    assert result.values_inserted == 3
    plate = h.run.plates[0]
    assert (plate.holder_kind, plate.holder_rows, plate.holder_columns, plate.format) == (
        HolderKind.CASSETTE,
        1,
        3,
        None,
    )
    assert plate.plate_number == 1
    assert [(w.row, w.column, w.label) for w in h.run.wells] == [
        ("A", 1, "protein alone"),
        ("A", 2, "ABC-0000001"),
        ("A", 3, "ABC-0000002"),
    ]
    assert [(w.well_type, w.batch_id, w.dose) for w in h.run.wells] == [
        (WellType.REFERENCE, None, None),
        (WellType.SAMPLE, h.batch.id, 10),
        (WellType.SAMPLE, h.batch2.id, 10),
    ]
    assert all(w.plate_id == plate.id for w in h.run.wells)

    saved = h.curve_repo.save_bulk.await_args.args[0]
    assert {c.well_id for c in saved} == {w.id for w in h.run.wells}
    assert saved[0].x == h.reader._export.curves[0].x
    assert [(c.channel_key, c.channel_order) for c in saved[:2]] == [("ratio", 0), ("signal", 1)]
    assert [c.x_label for c in saved[:2]] == ["Temperature", None]
    assert all(c.workspace_id == h.ws and c.run_id == h.run.id for c in saved)
    assert [len(c.reported) for c in saved[:2]] == [1, 0]

    readouts = h.readout_repo.save_bulk.await_args.args[0]
    assert all(r.well_id and r.readout_definition_id == h.tm1.id for r in readouts)
    assert [r.value.value for r in readouts] == [51.0, 52.0, 53.0]
    assert readouts[0].batch_id is None and readouts[0].molecule_id is None
    assert readouts[1].batch_id == h.batch.id and readouts[1].molecule_id == h.batch.molecule_id
    assert all(r.workspace_id == h.ws and r.run_id == h.run.id for r in readouts)

    assert h.calls == ["run", "rd", "curve"] and h.uow.committed
    h.batch_repo.find_by_ids.assert_awaited_once_with(h.ws, [h.batch.id, h.batch2.id])
    (event,) = h.dispatcher.dispatch_all.await_args.args[0]
    assert isinstance(event, RunInstrumentFileImported) and event.curves == 6
    assert (event.positions, event.readout_values, event.file_name) == (3, 3, "run.bin")
    assert result.attachment_id == h.attachment_id and result.attachment_warning is None
    upload = h.upload_attachment.await_args.args[0]
    assert (upload.workspace_id, upload.attachable_id, upload.file_data) == (h.ws, h.run.id, b"x")


async def test_unused_position_creates_nothing():
    h = Harness()
    positions = (*h.positions[:2], replace(h.positions[2], used=False))
    result = (await h(h.command(positions=positions))).unwrap()

    assert (result.positions_created, result.curves_created, result.values_inserted) == (2, 4, 2)
    assert [w.column for w in h.run.wells] == [1, 2]
    assert len(h.curve_repo.save_bulk.await_args.args[0]) == 4
    assert {r.well_id for r in h.readout_repo.save_bulk.await_args.args[0]} == {
        w.id for w in h.run.wells
    }
    h.batch_repo.find_by_ids.assert_awaited_once_with(h.ws, [h.batch.id])


async def test_position_without_batch_keeps_label_and_curves():
    h = Harness()
    positions = (h.positions[0], replace(h.positions[1], batch_id=None), h.positions[2])
    (await h(h.command(positions=positions))).unwrap()

    well = h.run.wells[1]
    assert well.batch_id is None and well.label == "ABC-0000001"
    readout = next(r for r in h.readout_repo.save_bulk.await_args.args[0] if r.well_id == well.id)
    assert readout.molecule_id is None and readout.batch_id is None
    curves = [c for c in h.curve_repo.save_bulk.await_args.args[0] if c.well_id == well.id]
    assert len(curves) == 2


async def test_unmapped_series_stays_on_the_curve_only():
    h = Harness()
    result = (await h(h.command(series=()))).unwrap()

    assert result.values_inserted == 0
    h.readout_repo.save_bulk.assert_not_awaited()
    ratio_curves = [
        c for c in h.curve_repo.save_bulk.await_args.args[0] if c.channel_key == "ratio"
    ]
    assert all(c.reported for c in ratio_curves)
    assert ratio_curves[0].reported[0].label == "Onset #1 for Ratio"
    h.engine.compute_for_run.assert_not_awaited()


async def test_engine_runs_only_when_values_were_written():
    h = Harness()
    (await h()).unwrap()
    h.engine.compute_for_run.assert_awaited_once_with(h.run.id, workspace_id=h.ws)

    h = Harness()
    (await h(h.command(series=()))).unwrap()
    h.engine.compute_for_run.assert_not_awaited()


async def test_engine_failure_becomes_compute_warning(capsys):
    h = Harness()
    h.engine.compute_for_run.return_value = Failure(ValidationError("formula broke"))
    result = (await h()).unwrap()
    # The user gets a plain sentence; the engine's reason goes to the log only.
    assert result.compute_warning == COMPUTE_FAILED
    assert "Recompute" in result.compute_warning
    logged = capsys.readouterr()
    assert "formula broke" in logged.out + logged.err


ATTACH_FAILED = "The file could not be attached. Upload it on the Files tab."


async def test_first_import_keeps_the_file_name():
    h = Harness()
    result = (await h()).unwrap()
    assert h.upload_attachment.await_args.args[0].file_name == "run.bin"
    assert result.stored_file_name is None
    h.attachment_repo.find_by_entity.assert_awaited_once_with(h.ws, AttachableType.RUN, h.run.id)


async def test_second_import_of_the_same_name_is_stored_numbered():
    h = Harness()
    h.attachment_repo.find_by_entity.return_value = [SimpleNamespace(file_name="run.bin")]
    result = (await h()).unwrap()
    assert h.upload_attachment.await_args.args[0].file_name == "run (2).bin"
    assert result.stored_file_name == "run (2).bin"
    assert result.attachment_id == h.attachment_id and result.attachment_warning is None


async def test_attachment_failure_is_a_plain_warning_not_a_failure():
    h = Harness()
    h.upload_attachment.return_value = Failure(ValidationError("storage full"))
    result = await h()
    assert isinstance(result, Success)
    assert result.unwrap().attachment_warning == ATTACH_FAILED
    assert result.unwrap().attachment_id is None
    assert result.unwrap().stored_file_name is None


async def test_attachment_exception_is_a_plain_warning_not_a_failure():
    h = Harness()
    h.upload_attachment.side_effect = RuntimeError(
        "Database constraint violated: uq_attachment_entity_filename"
    )
    result = (await h()).unwrap()
    assert result.attachment_warning == ATTACH_FAILED
    assert result.values_inserted == 3


async def test_run_not_found():
    h = Harness()
    h.run_repo.find_by_id_in_workspace.return_value = None
    assert isinstance((await h()).failure(), NotFoundError)
    h.run_repo.find_by_id_in_workspace.assert_awaited_once_with(h.ws, h.run.id)
    h.assert_nothing_written()


async def test_protocol_not_found():
    h = Harness()
    h.protocol_repo.find_by_id_in_workspace.return_value = None
    failure = (await h()).failure()
    assert isinstance(failure, NotFoundError) and "Protocol" in str(failure)
    h.protocol_repo.find_by_id_in_workspace.assert_awaited_once_with(h.ws, h.run.protocol_id)
    h.assert_nothing_written()


@pytest.mark.parametrize("case", ["locked", "completed", "has_holder", "wellless"])
async def test_conflicts_write_nothing(case):
    h = Harness()
    if case == "locked":
        h.run.is_locked = True
    elif case == "completed":
        h.run.status = RunStatus.COMPLETED
    elif case == "has_holder":
        h.run.plates.append(Plate(run_id=h.run.id, plate_number=1))
    else:
        h.readout_repo.has_wellless_rows.return_value = True

    assert isinstance((await h()).failure(), ConflictError)
    h.run_repo.save.assert_not_awaited()
    h.readout_repo.save_bulk.assert_not_awaited()
    h.curve_repo.save_bulk.assert_not_awaited()
    assert h.uow.committed is False and h.reader.called is False


async def test_viewer_raises_authorization_error():
    h = Harness()
    with pytest.raises(AuthorizationError):
        await h(auth=FakeAuth(role="viewer", workspace_id=h.ws))
    h.assert_nothing_written()


async def test_other_workspace_raises_not_found():
    h = Harness()
    with pytest.raises(NotFoundError):
        await h(auth=FakeAuth())
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()


async def test_batch_not_in_workspace_is_not_found_and_nothing_written():
    h = Harness()
    foreign_batch_id = uuid.uuid4()  # the id belongs to another workspace
    h.batch_repo.find_by_ids.side_effect = None
    h.batch_repo.find_by_ids.return_value = []
    positions = (h.positions[0], replace(h.positions[1], batch_id=foreign_batch_id))
    positions = (*positions, replace(h.positions[2], used=False))

    failure = (await h(h.command(positions=positions))).failure()
    assert isinstance(failure, NotFoundError) and str(foreign_batch_id) in str(failure)
    h.batch_repo.find_by_ids.assert_awaited_once_with(h.ws, [foreign_batch_id])
    h.assert_nothing_written()


async def test_readout_with_different_unit_is_refused():
    h = Harness()
    series = (SeriesMapping("ratio", "onset", 1, h.percent.id),)
    failure = (await h(h.command(series=series))).failure()
    assert isinstance(failure, ValidationError)
    assert "°C" in str(failure) and "%" in str(failure)
    h.assert_nothing_written()


@pytest.mark.parametrize("which", ["calculated", "text", "foreign"])
async def test_calculated_non_numeric_or_foreign_readout_is_refused(which):
    h = Harness()
    target = {
        "calculated": h.calculated.id,
        "text": h.text.id,
        "foreign": uuid.uuid4(),
    }[which]
    series = (SeriesMapping("ratio", "onset", 1, target),)
    assert isinstance((await h(h.command(series=series))).failure(), ValidationError)
    h.assert_nothing_written()


async def test_two_series_on_one_readout_is_refused():
    reported = tuple(_reported(c, ordinal=o) for c in (1, 2, 3) for o in (1, 2))
    h = Harness(export=_export(reported=reported))
    series = (
        SeriesMapping("ratio", "onset", 1, h.tm1.id),
        SeriesMapping("ratio", "onset", 2, h.tm1.id),
    )
    failure = (await h(h.command(series=series))).failure()
    assert isinstance(failure, ValidationError)
    assert failure.message == (
        f"Readout '{h.tm1.name}' is chosen for more than one reported value. "
        "Choose a different readout for each reported value."
    )
    h.assert_nothing_written()


async def test_two_series_on_one_unknown_readout_name_no_identifier():
    reported = tuple(_reported(c, ordinal=o) for c in (1, 2, 3) for o in (1, 2))
    h = Harness(export=_export(reported=reported))
    foreign = uuid.uuid4()
    series = (
        SeriesMapping("ratio", "onset", 1, foreign),
        SeriesMapping("ratio", "onset", 2, foreign),
    )
    failure = (await h(h.command(series=series))).failure()
    assert isinstance(failure, ValidationError) and str(foreign) not in failure.message
    assert failure.message.startswith("A readout is chosen for more than one reported value.")
    h.assert_nothing_written()


async def test_series_not_in_file_is_refused():
    h = Harness()
    series = (SeriesMapping("ratio", "onset", 3, h.tm1.id),)
    failure = (await h(h.command(series=series))).failure()
    assert isinstance(failure, ValidationError)
    # No internal signal key or grouping in the sentence.
    assert failure.message == (
        "A reported value chosen for a readout is not in this file. Choose the file again."
    )
    h.assert_nothing_written()


async def test_position_not_in_file_is_refused():
    h = Harness()
    positions = (*h.positions, PositionLabelling(row=1, column=9))
    failure = (await h(h.command(positions=positions))).failure()
    assert isinstance(failure, ValidationError)
    assert position_label(HolderKind.CASSETTE, "A", 9) in str(failure)
    h.assert_nothing_written()


async def test_file_position_missing_from_labelling_is_refused():
    h = Harness()
    failure = (await h(h.command(positions=h.positions[:2]))).failure()
    assert isinstance(failure, ValidationError)
    assert position_label(HolderKind.CASSETTE, "A", 3) in str(failure)
    h.assert_nothing_written()


async def test_position_named_twice_is_refused():
    h = Harness()
    positions = (*h.positions, replace(h.positions[0], label="again"))
    failure = (await h(h.command(positions=positions))).failure()
    assert isinstance(failure, ValidationError)
    assert position_label(HolderKind.CASSETTE, "A", 1) in str(failure)
    h.assert_nothing_written()


async def test_non_finite_curve_value_is_refused_and_nothing_written():
    h = Harness(export=_export(y=(1.0, float("nan"), 1.2)))
    assert isinstance((await h()).failure(), ValidationError)
    h.assert_nothing_written()


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
async def test_non_finite_reported_value_without_curve_is_refused(value):
    # The mapped series' channel has no curve at the position, so no curve invariant
    # catches the value: the import itself must refuse it.
    export = replace(
        _export(reported=(_reported(1), _reported(2, value=value), _reported(3))),
        curves=tuple(c for c in _export().curves if c.channel != "ratio"),
    )
    h = Harness(export=export)
    failure = (await h()).failure()
    assert isinstance(failure, ValidationError) and "finite" in str(failure)
    h.assert_nothing_written()


async def test_label_too_long_is_refused_and_nothing_written():
    h = Harness()
    positions = (replace(h.positions[0], label="x" * 201), *h.positions[1:])
    failure = (await h(h.command(positions=positions))).failure()
    assert isinstance(failure, ValidationError)
    assert failure.message == "Position label must be at most 200 characters"
    h.assert_nothing_written()


async def test_note_is_stored_on_the_position():
    h = Harness()
    positions = (h.positions[0], replace(h.positions[1], note="strongly coloured"), h.positions[2])
    (await h(h.command(positions=positions))).unwrap()
    assert [w.note for w in h.run.wells] == [None, "strongly coloured", None]


async def test_note_over_1000_characters_is_refused_and_nothing_written():
    h = Harness()
    positions = (replace(h.positions[0], note="x" * 1001), *h.positions[1:])
    failure = (await h(h.command(positions=positions))).failure()
    assert isinstance(failure, ValidationError)
    assert failure.message == "Position note must be at most 1000 characters"
    h.assert_nothing_written()


async def test_reported_value_for_undeclared_channel_is_a_warning():
    reported = (*(_reported(c) for c in (1, 2, 3)), _reported(1, channel="ghost"))
    h = Harness(export=_export(reported=reported))
    result = (await h()).unwrap()
    assert result.warnings == (
        "Reported value 'Onset #1 for Ghost' belongs to a signal the file has no "
        "traces for. It is skipped.",
    )
    assert result.values_inserted == 3


async def test_used_position_without_a_curve_on_a_channel_is_a_warning():
    export = _export()
    # Position 2 has no curve on the second channel; position 3 has none at all but is unused.
    curves = tuple(
        c for c in export.curves if (c.column, c.channel) != (2, "signal") and c.column != 3
    )
    h = Harness(export=replace(export, curves=curves))
    positions = (*h.positions[:2], replace(h.positions[2], used=False))
    result = (await h(h.command(positions=positions))).unwrap()

    label = position_label(HolderKind.CASSETTE, "A", 2)
    assert result.warnings == (
        f"{label} has no Signal trace in the file. Mapped reported values can still be imported.",
    )
    assert (result.positions_created, result.curves_created) == (2, 3)


async def test_holder_that_is_not_a_plate_clears_the_run_plate_format():
    h = Harness()
    h.run.plate_format = PlateFormat.F96
    (await h()).unwrap()
    assert h.run.plate_format is None


async def test_plate_holder_keeps_the_run_plate_format():
    export = _export()
    h = Harness(export=replace(export, holder=HolderLayout(HolderKind.PLATE, 1, 3)))
    h.run.plate_format = PlateFormat.F96
    (await h()).unwrap()
    assert h.run.plate_format is PlateFormat.F96


async def test_transition_series_cannot_be_mapped():
    h = Harness(export=_export(reported=tuple(_reported(c, kind="transition") for c in (1, 2, 3))))
    series = (SeriesMapping("ratio", "transition", 1, h.tm1.id),)
    failure = (await h(h.command(series=series))).failure()
    assert isinstance(failure, ValidationError) and "is a melting step" in failure.message
    h.assert_nothing_written()


async def test_import_creates_one_unreviewed_instrument_step_per_transition():
    reported = (
        *(_reported(c, kind="transition", value=60.0 + c) for c in (1, 2, 3)),
        _reported(2, kind="transition", ordinal=2, value=80.0),
        _reported(1, channel="ghost", kind="transition"),  # undeclared channel: no step
    )
    h = Harness(export=_export(reported=reported))
    positions = (*h.positions[:2], replace(h.positions[2], used=False))
    (await h(h.command(positions=positions, series=()))).unwrap()

    steps = h.step_repo.save_bulk.await_args.args[0]
    assert len(steps) == 3  # position 3 is unused
    assert {s.run_id for s in steps} == {h.run.id} and {s.workspace_id for s in steps} == {h.ws}
    assert {s.channel_key for s in steps} == {"ratio"}
    assert sorted(s.value for s in steps) == [61.0, 62.0, 80.0]
    assert all(
        s.source.value == "instrument"
        and s.status.value == "unreviewed"
        and s.instrument_value == s.value
        for s in steps
    )
    assert h.calls.index("step") > h.calls.index("curve")  # saved with the curves, then commit
    assert h.uow.committed is True
    h.engine.compute_for_run.assert_awaited_once()  # window rows come from steps alone


async def test_onsets_do_not_become_steps():
    h = Harness()
    (await h()).unwrap()
    h.step_repo.save_bulk.assert_not_awaited()


async def test_reported_transition_without_a_trace_makes_no_step():
    # Position 2 has no trace on "ratio": its transition cannot be drawn or reviewed.
    export = _export(
        reported=tuple(_reported(c, kind="transition", value=60.0 + c) for c in (1, 2, 3))
    )
    curves = tuple(c for c in export.curves if (c.column, c.channel) != (2, "ratio"))
    h = Harness(export=replace(export, curves=curves))
    (await h(h.command(series=()))).unwrap()

    steps = h.step_repo.save_bulk.await_args.args[0]
    assert sorted(s.value for s in steps) == [61.0, 63.0]
