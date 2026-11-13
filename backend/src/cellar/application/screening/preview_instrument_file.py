"""PreviewInstrumentFile: read an instrument file and propose how to label it.

Returns the holder, its positions with a suggested molecule and batch, the
channels, and the reported series with a pre-filled readout where a readout is
named like the series. Writes nothing; ``ImportInstrumentFile`` takes the
user's confirmed labelling with the same file.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.instrument_export import (
    ExportChannel,
    InstrumentReaders,
    read_instrument_file,
)
from cellar.application.screening.instrument_import_plan import (
    ReportedSeries,
    label_lookup_candidates,
    missing_curve_warnings,
    refuse_instrument_import,
    reported_series,
    suggest_readout,
)
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.enums import HolderKind, ReadoutDataType
from cellar.domain.screening_assay.holder import holder_label, position_label, row_letters
from cellar.domain.screening_assay.melt_window import STEP_KIND
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class BatchOption:
    batch_id: uuid.UUID
    batch_number: str


@dataclass(frozen=True)
class PositionSuggestion:
    molecule_id: uuid.UUID
    molecule_name: str
    registration_number: str
    batches: tuple[BatchOption, ...]
    batch_id: uuid.UUID | None  # set only when the molecule has exactly one batch


@dataclass(frozen=True)
class PositionPreview:
    row: int
    column: int
    position_label: str
    label: str
    suggestion: PositionSuggestion | None


@dataclass(frozen=True)
class SeriesPreview:
    series: ReportedSeries
    suggested_readout_definition_id: uuid.UUID | None


@dataclass(frozen=True)
class ReadoutOption:
    """A numeric, non-calculated readout of the run's protocol."""

    id: uuid.UUID
    name: str
    unit: str | None


@dataclass(frozen=True)
class InstrumentFilePreview:
    reader: str
    reader_label: str
    holder_kind: HolderKind
    holder_rows: int
    holder_columns: int
    holder_label: str
    dose_unit: str
    positions: tuple[PositionPreview, ...]
    channels: tuple[ExportChannel, ...]
    series: tuple[SeriesPreview, ...]
    readouts: tuple[ReadoutOption, ...]
    settings: Mapping[str, str]
    warnings: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class PreviewInstrumentFileQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    filename: str
    content: bytes


class PreviewInstrumentFile:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        readout_repo: ReadoutDataRepository,
        molecule_repo: MoleculeRepository,
        batch_repo: BatchRepository,
        readers: InstrumentReaders,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._readout_repo = readout_repo
        self._molecule_repo = molecule_repo
        self._batch_repo = batch_repo
        self._readers = readers

    async def __call__(
        self, input: PreviewInstrumentFileQuery, auth: AuthContext | None = None
    ) -> Result[InstrumentFilePreview, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        ws = input.workspace_id
        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(ws, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            if (refusal := await refuse_instrument_import(run, self._readout_repo)) is not None:
                return Failure(refusal)
            protocol = await self._protocol_repo.find_by_id_in_workspace(ws, run.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(run.protocol_id)))

            read = read_instrument_file(self._readers, input.content, input.filename)
            if isinstance(read, Failure):
                return read
            reader, export = read.unwrap()

            suggest = _Suggester(ws, self._molecule_repo, self._batch_repo)
            positions = tuple(
                [
                    PositionPreview(
                        row=p.row,
                        column=p.column,
                        position_label=position_label(
                            export.holder.kind, row_letters(p.row), p.column
                        ),
                        label=p.label.strip(),
                        suggestion=await suggest(p.label),
                    )
                    for p in export.positions
                ]
            )

        definitions = protocol.readout_definitions
        series, warnings = reported_series(export)
        series = [s for s in series if s.kind != STEP_KIND]  # steps are not mapped to readouts
        warnings += missing_curve_warnings(export, ((p.row, p.column) for p in export.positions))
        return Success(
            InstrumentFilePreview(
                reader=reader.id,
                reader_label=reader.label,
                holder_kind=export.holder.kind,
                holder_rows=export.holder.rows,
                holder_columns=export.holder.columns,
                holder_label=holder_label(
                    export.holder.kind, export.holder.rows, export.holder.columns
                ),
                dose_unit=str(protocol.dose_unit),
                positions=positions,
                channels=export.channels,
                series=tuple(SeriesPreview(s, suggest_readout(s, definitions)) for s in series),
                readouts=tuple(
                    ReadoutOption(id=d.id, name=d.name, unit=d.unit)
                    for d in definitions
                    if d.data_type == ReadoutDataType.NUMERIC and not d.is_calculated
                ),
                settings=export.settings,
                warnings=tuple(warnings),
            )
        )


class _Suggester:
    """Position label -> suggestion, with one lookup per distinct identifier and molecule."""

    def __init__(
        self, ws: uuid.UUID, molecule_repo: MoleculeRepository, batch_repo: BatchRepository
    ) -> None:
        self._ws = ws
        self._molecule_repo = molecule_repo
        self._batch_repo = batch_repo
        self._molecules: dict[str, Molecule | None] = {}
        self._suggestions: dict[uuid.UUID, PositionSuggestion] = {}

    async def __call__(self, label: str) -> PositionSuggestion | None:
        for candidate in label_lookup_candidates(label):
            if candidate not in self._molecules:
                self._molecules[candidate] = await self._molecule_repo.find_by_identifier(
                    self._ws, candidate
                )
            molecule = self._molecules[candidate]
            if molecule is not None:
                return await self._suggestion(molecule)
        return None

    async def _suggestion(self, molecule: Molecule) -> PositionSuggestion:
        if molecule.id not in self._suggestions:
            batches = await self._batch_repo.find_by_molecule(self._ws, molecule.id)
            self._suggestions[molecule.id] = PositionSuggestion(
                molecule_id=molecule.id,
                molecule_name=molecule.name,
                registration_number=molecule.registration_number.value,
                batches=tuple(BatchOption(b.id, b.batch_number.value) for b in batches),
                batch_id=batches[0].id if len(batches) == 1 else None,
            )
        return self._suggestions[molecule.id]
