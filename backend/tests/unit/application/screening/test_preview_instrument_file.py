"""Unit tests for PreviewInstrumentFile."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date
from types import SimpleNamespace, TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest

from cellar.application.screening.instrument_export import (
    ExportChannel,
    ExportCurve,
    ExportPosition,
    HolderLayout,
    InstrumentExport,
    InstrumentReaders,
    ReportedValue,
)
from cellar.application.screening.preview_instrument_file import (
    PreviewInstrumentFile,
    PreviewInstrumentFileQuery,
)
from cellar.domain.screening_assay.enums import HolderKind, ReadoutDataType, RunStatus
from cellar.domain.screening_assay.holder import holder_label, position_label
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.screening_assay.run import Plate, Run
from cellar.domain.shared.enums import ConcentrationUnit
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from cellar.domain.shared.value_objects import BatchNumber, RegistrationNumber
from tests.fakes.fake_auth import FakeAuth


class FakeUoW:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list:
        self.committed = True
        return []

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
    ExportChannel("ratio", "Ratio", "°C", None),
    ExportChannel("signal", "Signal", "°C", "a.u."),
)


def _reported(column: int, channel: str = "ratio", kind: str = "transition") -> ReportedValue:
    label = f"{kind.title()} #1 for {channel.title()}"
    return ReportedValue(
        row=1,
        column=column,
        channel=channel,
        kind=kind,
        ordinal=1,
        label=label,
        value=55.0,
        unit="°C",
    )


def _export(
    labels: tuple[str, ...] = ("", "ABC-0000001", "ABC-0000002"),
    reported: tuple[ReportedValue, ...] | None = None,
) -> InstrumentExport:
    columns = range(1, len(labels) + 1)
    return InstrumentExport(
        reader="stub",
        holder=HolderLayout(HolderKind.CASSETTE, 1, len(labels)),
        positions=tuple(
            ExportPosition(1, c, label) for c, label in zip(columns, labels, strict=True)
        ),
        channels=CHANNELS,
        curves=tuple(
            ExportCurve(1, c, ch.key, (20.0, 21.0, 22.0), (1.0, 1.1, 1.2))
            for c in columns
            for ch in CHANNELS
        ),
        reported=tuple(_reported(c) for c in columns) if reported is None else reported,
        settings={"Start temperature": "20 °C"},
    )


class StubReader:
    id = "stub"
    label = "Stub format"

    def __init__(self, export: InstrumentExport, *, recognises: bool = True) -> None:
        self._export = export
        self._recognises = recognises
        self.called = False

    def recognises(self, content: bytes, filename: str) -> bool:
        self.called = True
        return self._recognises

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


def _molecule(name: str = "Compound one") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), name=name, registration_number=RegistrationNumber(value="REG-0001")
    )


def _batch(molecule: SimpleNamespace, number: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), molecule_id=molecule.id, batch_number=BatchNumber(value=number)
    )


class Harness:
    def __init__(
        self,
        *,
        export: InstrumentExport | None = None,
        run_status: RunStatus = RunStatus.DRAFT,
        locked: bool = False,
        with_holder: bool = False,
        run_missing: bool = False,
        definitions: list[ReadoutDefinition] | None = None,
        molecules: dict[str, SimpleNamespace] | None = None,
        batches: dict[uuid.UUID, list[SimpleNamespace]] | None = None,
        recognises: bool = True,
    ) -> None:
        self.auth = FakeAuth()
        self.ws = self.auth.workspace_id
        self.run = Run(
            workspace_id=self.ws,
            protocol_id=uuid.uuid4(),
            run_date=date(2026, 11, 12),
            operator=uuid.uuid4(),
            status=run_status,
            is_locked=locked,
        )
        if with_holder:
            self.run.plates.append(Plate(run_id=self.run.id, plate_number=1))
        self.definitions = definitions if definitions is not None else []
        self.protocol = SimpleNamespace(
            id=self.run.protocol_id,
            dose_unit=ConcentrationUnit.UM,
            readout_definitions=self.definitions,
        )
        self.uow = FakeUoW()
        self.run_repo = AsyncMock()
        self.run_repo.find_by_id_in_workspace = AsyncMock(
            return_value=None if run_missing else self.run
        )
        self.protocol_repo = AsyncMock()
        self.protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=self.protocol)
        self.readout_repo = AsyncMock()
        self.readout_repo.has_wellless_rows = AsyncMock(return_value=False)
        mols = molecules or {}
        self.molecule_repo = AsyncMock()
        self.molecule_repo.find_by_identifier = AsyncMock(
            side_effect=lambda ws, identifier: mols.get(identifier)
        )
        bats = batches or {}
        self.batch_repo = AsyncMock()
        self.batch_repo.find_by_molecule = AsyncMock(
            side_effect=lambda ws, molecule_id: bats.get(molecule_id, [])
        )
        self.reader = StubReader(export or _export(), recognises=recognises)
        self.uc = PreviewInstrumentFile(
            uow=self.uow,
            run_repo=self.run_repo,
            protocol_repo=self.protocol_repo,
            readout_repo=self.readout_repo,
            molecule_repo=self.molecule_repo,
            batch_repo=self.batch_repo,
            readers=InstrumentReaders((self.reader,)),
        )
        self.query = PreviewInstrumentFileQuery(
            workspace_id=self.ws, run_id=self.run.id, filename="run.bin", content=b"x"
        )

    async def __call__(self, auth: FakeAuth | None = None):
        return await self.uc(self.query, auth=auth or self.auth)


async def test_success_lists_positions_channels_series_and_readouts():
    numeric = _definition("Melting point")
    h = Harness(
        definitions=[
            numeric,
            _definition("Comment", None, data_type=ReadoutDataType.TEXT),
            _definition("Derived", calculated=True),
        ]
    )
    preview = (await h()).unwrap()

    assert (preview.reader, preview.reader_label) == ("stub", "Stub format")
    assert (preview.holder_kind, preview.holder_rows, preview.holder_columns) == (
        HolderKind.CASSETTE,
        1,
        3,
    )
    assert preview.holder_label == holder_label(HolderKind.CASSETTE, 1, 3)
    assert [p.position_label for p in preview.positions] == [
        position_label(HolderKind.CASSETTE, "A", n) for n in (1, 2, 3)
    ]
    assert [(p.row, p.column, p.label) for p in preview.positions] == [
        (1, 1, ""),
        (1, 2, "ABC-0000001"),
        (1, 3, "ABC-0000002"),
    ]
    assert preview.channels == CHANNELS
    assert [s.series.key for s in preview.series] == [("ratio", "transition", 1)]
    assert preview.series[0].series.count == 3
    assert [(r.id, r.name, r.unit) for r in preview.readouts] == [
        (numeric.id, "Melting point", "°C")
    ]
    assert preview.settings == {"Start temperature": "20 °C"}
    assert preview.warnings == ()
    assert preview.dose_unit == "uM" and h.uow.committed is False
    h.run_repo.find_by_id_in_workspace.assert_awaited_once_with(h.ws, h.run.id)
    h.protocol_repo.find_by_id_in_workspace.assert_awaited_once_with(h.ws, h.run.protocol_id)


async def test_exact_identifier_match_with_one_batch_is_preselected():
    mol = _molecule()
    only_batch = _batch(mol, "ABC-0000001-001")
    h = Harness(
        export=_export(("ABC-0000001",)),
        molecules={"ABC-0000001": mol},
        batches={mol.id: [only_batch]},
    )
    preview = (await h()).unwrap()

    suggestion = preview.positions[0].suggestion
    assert suggestion is not None
    assert suggestion.molecule_id == mol.id and suggestion.batch_id == only_batch.id
    assert suggestion.molecule_name == "Compound one"
    assert suggestion.registration_number == "REG-0001"
    assert [(b.batch_id, b.batch_number) for b in suggestion.batches] == [
        (only_batch.id, "ABC-0000001-001")
    ]
    h.batch_repo.find_by_molecule.assert_awaited_once_with(h.ws, mol.id)


async def test_bracketed_suffix_falls_back_to_the_part_before_it():
    mol = _molecule()
    h = Harness(
        export=_export(("ABC-0000001 (Old)",)),
        molecules={"ABC-0000001": mol},
        batches={mol.id: [_batch(mol, "ABC-0000001-001")]},
    )
    preview = (await h()).unwrap()

    assert [c.args[1] for c in h.molecule_repo.find_by_identifier.await_args_list] == [
        "ABC-0000001 (Old)",
        "ABC-0000001",
    ]
    assert all(c.args[0] == h.ws for c in h.molecule_repo.find_by_identifier.await_args_list)
    suggestion = preview.positions[0].suggestion
    assert suggestion is not None and suggestion.molecule_id == mol.id


async def test_several_batches_none_preselected():
    mol = _molecule()
    h = Harness(
        export=_export(("ABC-0000001",)),
        molecules={"ABC-0000001": mol},
        batches={mol.id: [_batch(mol, f"ABC-0000001-00{n}") for n in (1, 2, 3)]},
    )
    suggestion = (await h()).unwrap().positions[0].suggestion

    assert suggestion is not None
    assert len(suggestion.batches) == 3 and suggestion.batch_id is None


async def test_same_label_is_looked_up_once():
    mol = _molecule()
    h = Harness(
        export=_export(("ABC-0000001", "ABC-0000001", "ABC-0000009")),
        molecules={"ABC-0000001": mol},
        batches={mol.id: [_batch(mol, "ABC-0000001-001")]},
    )
    preview = (await h()).unwrap()

    assert [c.args[1] for c in h.molecule_repo.find_by_identifier.await_args_list] == [
        "ABC-0000001",
        "ABC-0000009",
    ]
    assert [p.suggestion is not None for p in preview.positions] == [True, True, False]


async def test_blank_label_gets_no_suggestion_and_no_lookup():
    h = Harness(export=_export(("", "  ", "")))
    preview = (await h()).unwrap()

    assert all(p.suggestion is None and p.label == "" for p in preview.positions)
    h.molecule_repo.find_by_identifier.assert_not_awaited()


async def test_series_is_prefilled_only_on_name_match():
    matching = _definition("transition #1 for ratio")
    reported = (_reported(1), _reported(1, kind="onset"))
    h = Harness(
        export=_export(("",), reported=reported),
        definitions=[matching, _definition("Onset")],
    )
    preview = (await h()).unwrap()

    assert [(s.series.key, s.suggested_readout_definition_id) for s in preview.series] == [
        (("ratio", "transition", 1), matching.id),
        (("ratio", "onset", 1), None),
    ]


async def test_reported_value_for_undeclared_channel_warns_and_is_not_a_series():
    reported = (_reported(1), _reported(1, channel="ghost"))
    h = Harness(export=_export(("",), reported=reported))
    preview = (await h()).unwrap()

    assert [s.series.channel for s in preview.series] == ["ratio"]
    assert len(preview.warnings) == 1 and "ghost" in preview.warnings[0]


async def test_run_not_found():
    h = Harness(run_missing=True)
    assert isinstance((await h()).failure(), NotFoundError)
    assert h.reader.called is False


async def test_run_with_holder_is_conflict():
    h = Harness(with_holder=True)
    failure = (await h()).failure()
    assert isinstance(failure, ConflictError) and "Reset" in str(failure)
    assert h.reader.called is False


async def test_locked_run_is_conflict():
    h = Harness(locked=True, run_status=RunStatus.COMPLETED)
    assert isinstance((await h()).failure(), ConflictError)


async def test_completed_run_is_conflict():
    h = Harness(run_status=RunStatus.COMPLETED)
    failure = (await h()).failure()
    assert isinstance(failure, ConflictError) and "completed" in str(failure)


async def test_wellless_run_is_conflict():
    h = Harness()
    h.readout_repo.has_wellless_rows.return_value = True
    assert isinstance((await h()).failure(), ConflictError)
    h.readout_repo.has_wellless_rows.assert_awaited_once_with(h.ws, h.run.id)


async def test_protocol_not_found():
    h = Harness()
    h.protocol_repo.find_by_id_in_workspace.return_value = None
    failure = (await h()).failure()
    assert isinstance(failure, NotFoundError) and "Protocol" in str(failure)


async def test_viewer_raises_authorization_error():
    h = Harness()
    viewer = FakeAuth(role="viewer", workspace_id=h.ws)
    with pytest.raises(AuthorizationError):
        await h(auth=viewer)
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()


async def test_other_workspace_raises_not_found():
    h = Harness()
    with pytest.raises(NotFoundError):
        await h(auth=FakeAuth())
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()


async def test_unrecognised_file_is_validation_error():
    h = Harness(recognises=False)
    failure = (await h()).failure()
    assert isinstance(failure, ValidationError) and "Stub format" in str(failure)


async def test_position_without_a_curve_on_a_channel_is_a_warning():
    export = _export()
    curves = tuple(c for c in export.curves if (c.column, c.channel) != (3, "ratio"))
    h = Harness(export=replace(export, curves=curves))
    preview = (await h()).unwrap()

    label = position_label(HolderKind.CASSETTE, "A", 3)
    assert preview.warnings == (
        f"{label} has no Ratio curve in the file; nothing is stored for it on that channel",
    )
