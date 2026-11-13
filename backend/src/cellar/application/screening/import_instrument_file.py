"""ImportInstrumentFile: store an instrument file's curves and reported values on a run.

Companion to ``PreviewInstrumentFile``. Takes the same file plus the user's
labelling of its positions and the mapping of reported series to readouts,
checks everything before writing anything, then in one unit of work creates the
run's holder and used positions, the readout rows and the measured curves.
After the unit of work, as the other importers do, it runs the calculation
engine when readout rows were written and attaches the original file to the run.
"""

from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace

import structlog
from returns.result import Failure, Result, Success

from cellar.application.attachment.upload_attachment import (
    UploadAttachment,
    UploadAttachmentCommand,
)
from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.import_run_file_preview_store import _guess_content_type
from cellar.application.screening.instrument_export import (
    InstrumentExport,
    InstrumentReaders,
    read_instrument_file,
)
from cellar.application.screening.instrument_import_plan import (
    missing_curve_warnings,
    readout_mapping_error,
    refuse_instrument_import,
    reported_series,
)
from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.attachment.enums import AttachableType
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.holder import position_label, row_letters
from cellar.domain.screening_assay.measured_curve import MeasuredCurve, ReportedPoint
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.repository import (
    MeasuredCurveRepository,
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.enums import WellType
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.shared.value_objects import QualifiedValue

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PositionLabelling:
    row: int
    column: int
    used: bool = True
    label: str = ""
    well_type: WellType = WellType.SAMPLE
    batch_id: uuid.UUID | None = None
    dose: float | None = None
    note: str = ""


@dataclass(frozen=True)
class SeriesMapping:
    channel: str
    kind: str
    ordinal: int
    readout_definition_id: uuid.UUID


@dataclass(frozen=True)
class InstrumentLabelling:
    positions: tuple[PositionLabelling, ...]
    series: tuple[SeriesMapping, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ImportInstrumentFileCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    filename: str
    content: bytes
    labelling: InstrumentLabelling
    content_type: str | None = None


@dataclass(frozen=True)
class InstrumentImportResult:
    reader: str
    positions_created: int
    curves_created: int
    values_inserted: int
    warnings: tuple[str, ...] = ()
    compute_warning: str | None = None
    attachment_id: uuid.UUID | None = None
    attachment_warning: str | None = None


@dataclass(frozen=True)
class _Writes:
    plate: Plate
    wells: list[Well]
    readouts: list[ReadoutData]
    curves: list[MeasuredCurve]
    warnings: list[str]


class ImportInstrumentFile:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        readout_repo: ReadoutDataRepository,
        curve_repo: MeasuredCurveRepository,
        batch_repo: BatchRepository,
        readers: InstrumentReaders,
        upload_attachment: UploadAttachment,
        calculation_engine: ReadoutCalculationEngine,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._readout_repo = readout_repo
        self._curve_repo = curve_repo
        self._batch_repo = batch_repo
        self._readers = readers
        self._upload_attachment = upload_attachment
        self._calculation_engine = calculation_engine
        self._dispatcher = dispatcher

    async def __call__(
        self, input: ImportInstrumentFileCommand, auth: AuthContext | None = None
    ) -> Result[InstrumentImportResult, DomainError]:
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
            _, export = read.unwrap()

            planned = await self._plan(input, run, protocol.readout_definitions, export)
            if isinstance(planned, Failure):
                return planned
            writes = planned.unwrap()

            writes.plate.wells = writes.wells  # type: ignore[attr-defined]
            run.add_plate(writes.plate)
            if writes.plate.holder_kind is not HolderKind.PLATE:
                run.clear_plate_format()
            run.record_instrument_import(
                reader=export.reader,
                file_name=input.filename,
                positions=len(writes.wells),
                curves=len(writes.curves),
                readout_values=len(writes.readouts),
            )
            await self._run_repo.save(run)
            if writes.readouts:
                await self._readout_repo.save_bulk(writes.readouts)
            if writes.curves:
                await self._curve_repo.save_bulk(writes.curves)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)

        result = InstrumentImportResult(
            reader=export.reader,
            positions_created=len(writes.wells),
            curves_created=len(writes.curves),
            values_inserted=len(writes.readouts),
            warnings=tuple(writes.warnings),
        )
        _log.info(
            "instrument_file.imported",
            workspace_id=str(ws),
            run_id=str(run.id),
            reader=export.reader,
            positions=result.positions_created,
            curves=result.curves_created,
            values_inserted=result.values_inserted,
        )
        if result.values_inserted:
            computed = await self._calculation_engine.compute_for_run(run.id, workspace_id=ws)
            if isinstance(computed, Failure):
                result = replace(result, compute_warning=str(computed.failure()))
        return Success(await self._attach_raw_file(input, result, auth))

    async def _plan(
        self,
        input: ImportInstrumentFileCommand,
        run: Run,
        definitions: Sequence[ReadoutDefinition],
        export: InstrumentExport,
    ) -> Result[_Writes, DomainError]:
        """Check the labelling against the file and build every entity; write nothing."""
        ws = input.workspace_id
        kind = export.holder.kind
        labelling = input.labelling

        def name(row: int, column: int) -> str:
            return position_label(kind, row_letters(row), column)

        # Labelling against the file.
        file_keys = [(p.row, p.column) for p in export.positions]
        file_set = set(file_keys)
        named = Counter((p.row, p.column) for p in labelling.positions)
        problems = [
            (heading, keys)
            for heading, keys in (
                ("not in the file", [k for k in named if k not in file_set]),
                ("missing from the labelling", [k for k in file_keys if k not in named]),
                ("named more than once", [k for k, n in named.items() if n > 1]),
            )
            if keys
        ]
        if problems:
            return Failure(
                ValidationError(
                    "The labelling does not match the file's positions: "
                    + "; ".join(
                        f"{h}: {', '.join(name(*k) for k in keys)}" for h, keys in problems
                    )
                )
            )
        used = {(p.row, p.column): p for p in labelling.positions if p.used}

        # Batches of used positions, workspace-scoped.
        batch_ids = list(dict.fromkeys(p.batch_id for p in used.values() if p.batch_id))
        batches = (
            {b.id: b for b in await self._batch_repo.find_by_ids(ws, batch_ids)}
            if batch_ids
            else {}
        )
        if (missing := next((i for i in batch_ids if i not in batches), None)) is not None:
            return Failure(NotFoundError("Batch", str(missing)))

        # Series mapping.
        all_series, warnings = reported_series(export)
        warnings += missing_curve_warnings(export, (k for k in file_keys if k in used))
        series_by_key = {s.key: s for s in all_series}
        for m in labelling.series:
            if (m.channel, m.kind, m.ordinal) not in series_by_key:
                return Failure(
                    ValidationError(
                        f"The file has no reported series '{m.kind} #{m.ordinal}' "
                        f"on channel '{m.channel}'"
                    )
                )
        definitions_by_id = {d.id: d for d in definitions}
        twice = [
            i
            for i, n in Counter(m.readout_definition_id for m in labelling.series).items()
            if n > 1
        ]
        if twice:
            readout = definitions_by_id.get(twice[0])
            return Failure(
                ValidationError(
                    f"Readout '{readout.name if readout else twice[0]}' is chosen for more than "
                    "one reported series"
                )
            )
        for m in labelling.series:
            series = series_by_key[(m.channel, m.kind, m.ordinal)]
            error = readout_mapping_error(series, definitions_by_id.get(m.readout_definition_id))
            if error is not None:
                return Failure(error)
        mapped = {
            (m.channel, m.kind, m.ordinal): m.readout_definition_id for m in labelling.series
        }

        # Entities.
        try:
            plate = Plate(
                run_id=run.id,
                plate_number=1,
                format=None,
                holder_kind=kind,
                holder_rows=export.holder.rows,
                holder_columns=export.holder.columns,
            )
            wells = {
                key: Well(
                    plate_id=plate.id,
                    row=row_letters(p.row),
                    column=p.column,
                    well_type=p.well_type,
                    batch_id=p.batch_id,
                    dose=p.dose,
                    label=p.label,
                    note=p.note,
                )
                for key in file_keys
                if (p := used.get(key)) is not None
            }

            readouts: list[ReadoutData] = []
            reported_at: defaultdict[tuple[int, int, str], list[ReportedPoint]] = defaultdict(list)
            for v in export.reported:
                reported_at[(v.row, v.column, v.channel)].append(
                    ReportedPoint(v.kind, v.ordinal, v.label, v.value, v.unit)
                )
                well = wells.get((v.row, v.column))
                if well is not None and not math.isfinite(v.value):
                    raise ValidationError(
                        f"{name(v.row, v.column)}: reported value '{v.label}' "
                        "is not a finite number"
                    )
                definition_id = mapped.get((v.channel, v.kind, v.ordinal))
                if well is None or definition_id is None:
                    continue
                batch = batches.get(well.batch_id) if well.batch_id else None
                readouts.append(
                    ReadoutData(
                        workspace_id=ws,
                        run_id=run.id,
                        well_id=well.id,
                        batch_id=well.batch_id,
                        molecule_id=batch.molecule_id if batch else None,
                        readout_definition_id=definition_id,
                        value=QualifiedValue(value=v.value),
                    )
                )

            channels = {c.key: (order, c) for order, c in enumerate(export.channels)}
            curves: list[MeasuredCurve] = []
            for c in export.curves:
                well = wells.get((c.row, c.column))
                if well is None:
                    continue
                order, channel = channels[c.channel]
                curves.append(
                    MeasuredCurve(
                        workspace_id=ws,
                        run_id=run.id,
                        well_id=well.id,
                        channel_key=c.channel,
                        channel_label=channel.label,
                        x_unit=channel.x_unit,
                        y_unit=channel.y_unit,
                        x_label=channel.x_label,
                        channel_order=order,
                        x=c.x,
                        y=c.y,
                        reported=tuple(reported_at[(c.row, c.column, c.channel)]),
                        reader=export.reader,
                    )
                )
        except ValidationError as exc:
            return Failure(exc)

        return Success(
            _Writes(
                plate=plate,
                wells=list(wells.values()),
                readouts=readouts,
                curves=curves,
                warnings=warnings,
            )
        )

    async def _attach_raw_file(
        self,
        cmd: ImportInstrumentFileCommand,
        result: InstrumentImportResult,
        auth: AuthContext | None,
    ) -> InstrumentImportResult:
        """Persist the upload as a Run attachment; warn (never fail) on error."""
        if auth is None:
            return replace(result, attachment_warning="no auth context — skipped")
        upload_cmd = UploadAttachmentCommand(
            workspace_id=cmd.workspace_id,
            attachable_type=AttachableType.RUN,
            attachable_id=cmd.run_id,
            uploaded_by=auth.user_id,
            file_name=cmd.filename,
            mime_type=cmd.content_type or _guess_content_type(cmd.filename),
            file_data=cmd.content,
        )
        try:
            attached = await self._upload_attachment(upload_cmd, auth=auth)
        except Exception as exc:
            _log.warning(
                "instrument_import.attachment_failed",
                run_id=str(cmd.run_id),
                workspace_id=str(cmd.workspace_id),
                file_name=cmd.filename,
                error=str(exc),
                exc_info=True,
            )
            return replace(result, attachment_warning=f"attachment failed: {exc}")
        if isinstance(attached, Failure):
            return replace(result, attachment_warning=str(attached.failure()))
        return replace(result, attachment_id=attached.unwrap().id)
