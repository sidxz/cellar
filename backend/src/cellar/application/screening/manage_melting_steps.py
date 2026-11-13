"""AddMeltingStep and ReviewMeltingStep: hand-made and reviewed melting steps.

Each change is audited in the same unit of work, then the run is recalculated so the
Tm and ΔTm rows follow. A failed recalculation does not undo the saved change; it comes
back as ``compute_warning``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from returns.result import Failure, Result, Success

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.audit_compliance.enums import AuditAction, OperationType
from cellar.domain.audit_compliance.models import AuditEntry
from cellar.domain.screening_assay.melting_step import MeltingStep, MeltingStepStatus
from cellar.domain.screening_assay.repository import (
    MeasuredCurveRepository,
    MeltingStepRepository,
    RunRepository,
)
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError

NOT_EDITABLE = "Melting steps can be changed only while the run is draft or in progress"
NO_TRACE = "This position has no trace for that signal"
COMPUTE_FAILED = (
    "The melting step was saved, but the calculations could not be updated. "
    "Select Recompute on the run to update them."
)

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class AddMeltingStepCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    well_id: uuid.UUID
    channel_key: str
    value: float
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class ReviewMeltingStepCommand(Command):
    workspace_id: uuid.UUID
    step_id: uuid.UUID
    expected_version: int
    status: MeltingStepStatus
    value: float
    reason: str | None = None


@dataclass(frozen=True)
class MeltingStepChange:
    step: MeltingStep
    recalculated: bool
    compute_warning: str | None = None


class _StepUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        curve_repo: MeasuredCurveRepository,
        step_repo: MeltingStepRepository,
        audit: AuditRecordingService,
        calculation_engine: ReadoutCalculationEngine,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._curve_repo = curve_repo
        self._step_repo = step_repo
        self._audit = audit
        self._calculation_engine = calculation_engine

    @staticmethod
    def _check_run(run: Run) -> DomainError | None:
        if run.is_locked:
            return ConflictError("This run is locked")
        if not run.calculated_positions_editable:
            return ConflictError(NOT_EDITABLE)
        return None

    async def _x_range(
        self, ws: uuid.UUID, well_id: uuid.UUID, channel_key: str
    ) -> tuple[float, float] | None:
        curves = await self._curve_repo.find_by_wells(ws, [well_id], channel_key=channel_key)
        curve = next((c for c in curves if c.well_id == well_id), None)
        return (min(curve.x), max(curve.x)) if curve else None

    async def _audit_and_commit(
        self,
        *,
        step: MeltingStep,
        run: Run,
        operation_type: OperationType,
        entries: list[AuditEntry],
        reason: str | None,
        user_id: uuid.UUID,
    ) -> None:
        await self._audit.record(
            workspace_id=step.workspace_id,
            operation_type=operation_type,
            entity_type="MeltingStep",
            entity_id=step.id,
            user_id=user_id,
            entries=entries,
            reason=reason,
            session=self._uow.session,
        )
        await self._uow.commit()

    async def _recalculate(self, step: MeltingStep, run: Run) -> MeltingStepChange:
        computed = await self._calculation_engine.compute_for_run(
            run.id, workspace_id=step.workspace_id
        )
        if isinstance(computed, Failure):
            _log.warning(
                "melting_step.compute_failed",
                run_id=str(run.id),
                workspace_id=str(step.workspace_id),
                reason=str(computed.failure()),
            )
            return MeltingStepChange(step, False, COMPUTE_FAILED)
        return MeltingStepChange(step, True)


class AddMeltingStep(_StepUseCase):
    async def __call__(
        self, input: AddMeltingStepCommand, auth: AuthContext | None = None
    ) -> Result[MeltingStepChange, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id
        user_id = auth.user_id if auth else None
        if user_id is None:
            return Failure(ValidationError("A user is required to add a melting step"))

        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(ws, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            if (refused := self._check_run(run)) is not None:
                return Failure(refused)
            x_range = await self._x_range(ws, input.well_id, input.channel_key)
            if x_range is None:
                return Failure(ValidationError(NO_TRACE))
            try:
                step = MeltingStep.manual(
                    workspace_id=ws,
                    run_id=run.id,
                    well_id=input.well_id,
                    channel_key=input.channel_key,
                    value=input.value,
                    x_range=x_range,
                    reason=input.reason,
                    by=user_id,
                )
            except ValidationError as exc:
                return Failure(exc)
            await self._step_repo.add(step)
            entries = [
                AuditEntry(
                    entity_type="MeltingStep",
                    entity_id=step.id,
                    field_name=name,
                    action=AuditAction.CREATE,
                    new_value=new,
                )
                for name, new in (("value", f"{step.value:.15g}"), ("status", step.status.value))
            ]
            await self._audit_and_commit(
                step=step,
                run=run,
                operation_type=OperationType.DATA_ENTRY,
                entries=entries,
                reason=step.reason,
                user_id=user_id,
            )
        return Success(await self._recalculate(step, run))


class ReviewMeltingStep(_StepUseCase):
    async def __call__(
        self, input: ReviewMeltingStepCommand, auth: AuthContext | None = None
    ) -> Result[MeltingStepChange, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id
        user_id = auth.user_id if auth else None
        if user_id is None:
            return Failure(ValidationError("A user is required to review a melting step"))

        async with self._uow:
            step = await self._step_repo.find_by_id(ws, input.step_id)
            if step is None:
                return Failure(NotFoundError("MeltingStep", str(input.step_id)))
            run = await self._run_repo.find_by_id_in_workspace(ws, step.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(step.run_id)))
            if (refused := self._check_run(run)) is not None:
                return Failure(refused)
            x_range = await self._x_range(ws, step.well_id, step.channel_key)
            if x_range is None:
                return Failure(ValidationError(NO_TRACE))
            try:
                changes = step.review(
                    status=input.status,
                    value=input.value,
                    reason=input.reason,
                    x_range=x_range,
                    by=user_id,
                )
            except ValidationError as exc:
                return Failure(exc)
            if not changes:
                return Success(MeltingStepChange(step, False))
            try:
                await self._step_repo.update(step, expected_version=input.expected_version)
            except ConflictError as exc:
                return Failure(exc)
            entries = [
                AuditEntry(
                    entity_type="MeltingStep",
                    entity_id=step.id,
                    field_name=name,
                    action=AuditAction.UPDATE,
                    old_value=old,
                    new_value=new,
                )
                for name, old, new in changes
            ]
            await self._audit_and_commit(
                step=step,
                run=run,
                operation_type=OperationType.PROPERTY_EDIT,
                entries=entries,
                reason=step.reason,
                user_id=user_id,
            )
        return Success(await self._recalculate(step, run))
