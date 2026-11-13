"""RelabelRunPositions: edit an instrument-imported run's positions after import.

The user sends, per position, the values they started from and the values to store.
Label and note change nothing calculated; role, batch and concentration do. A batch
change re-points that position's readout rows to the new batch and its molecule in the
same unit of work, and is refused when a campaign uses those rows. After a save that
changed a role, a batch or a concentration, the calculation engine runs for the run.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.screening_assay.holder import position_label
from cellar.domain.screening_assay.repository import (
    MeasuredCurveRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.screening_assay.run import PositionEdit
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError

NO_MEASURED_CURVES = (
    "This run has no measured curves. Positions can be edited here only on a run "
    "imported from an instrument file."
)


@dataclass(frozen=True, kw_only=True)
class RelabelRunPositionsCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    edits: tuple[PositionEdit, ...]
    reason: str | None = None


@dataclass(frozen=True)
class RelabelResult:
    positions_changed: int
    readouts_repointed: int
    recalculated: bool
    compute_warning: str | None = None


class RelabelRunPositions:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        readout_repo: ReadoutDataRepository,
        curve_repo: MeasuredCurveRepository,
        batch_repo: BatchRepository,
        campaign_repo: CampaignRepository,
        calculation_engine: ReadoutCalculationEngine,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._readout_repo = readout_repo
        self._curve_repo = curve_repo
        self._batch_repo = batch_repo
        self._campaign_repo = campaign_repo
        self._calculation_engine = calculation_engine
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RelabelRunPositionsCommand, auth: AuthContext | None = None
    ) -> Result[RelabelResult, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        ws = input.workspace_id
        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(ws, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            if not await self._curve_repo.list_channels(ws, run.id):
                return Failure(ConflictError(NO_MEASURED_CURVES))

            named = {
                b
                for e in input.edits
                for b in (e.expected.batch_id, e.new.batch_id)
                if b is not None
            }
            batches = {b.id: b for b in await self._batch_repo.find_by_ids(ws, list(named))}
            for edit in input.edits:
                if edit.new.batch_id is not None and edit.new.batch_id not in batches:
                    return Failure(NotFoundError("Batch", str(edit.new.batch_id)))

            wells = {w.id: w for w in run.wells}
            moving = [
                wells[e.well_id]
                for e in input.edits
                if e.well_id in wells and e.new.batch_id != wells[e.well_id].batch_id
            ]
            if moving:
                rows = await self._readout_repo.find_by_run(ws, run.id)
                moving_ids = {w.id for w in moving}
                row_well = {r.id: r.well_id for r in rows if r.well_id in moving_ids}
                used = await self._campaign_repo.find_names_using_readouts(ws, list(row_well))
                if used:
                    plates = {p.id: p for p in run.plates}
                    readout_id, name = next(iter(used.items()))
                    well = wells[row_well[readout_id]]
                    label = position_label(
                        plates[well.plate_id].holder_kind, well.row, well.column
                    )
                    return Failure(
                        ConflictError(
                            f"{label}: its values are used by campaign '{name}', "
                            "so its batch cannot be changed"
                        )
                    )

            try:
                changes = run.relabel_positions(
                    input.edits,
                    reason=input.reason,
                    batch_names={b.id: b.batch_number.value for b in batches.values()},
                )
            except (ValidationError, ConflictError) as exc:
                return Failure(exc)
            if not changes:
                return Success(RelabelResult(0, 0, False))

            await self._run_repo.save(run)
            repointed = 0
            for change in changes:
                if change.batch_changed:
                    batch_id = wells[change.well_id].batch_id
                    repointed += await self._readout_repo.repoint_well(
                        ws,
                        run.id,
                        change.well_id,
                        batch_id=batch_id,
                        molecule_id=batches[batch_id].molecule_id if batch_id else None,
                    )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)

        recalculated, warning = False, None
        if any(change.touches_calculation for change in changes):
            computed = await self._calculation_engine.compute_for_run(run.id, workspace_id=ws)
            if isinstance(computed, Failure):
                warning = str(computed.failure())
            else:
                recalculated = True
        return Success(RelabelResult(len(changes), repointed, recalculated, warning))
