"""AddMeltingStep, ReviewMeltingStep, AssignMeltingStep and AcceptMeltingSteps: melting
steps placed by hand, reviewed, assigned to a temperature window, and accepted many at once.

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
    ProtocolRepository,
    RunRepository,
)
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError

NOT_EDITABLE = "Peaks cannot be changed on an approved run"
LOCKED = "This run is locked"
NO_TRACE = "This position has no trace for that signal"
COMPUTE_FAILED = (
    "The peak was saved, but the calculations could not be updated. "
    "Select Recompute on the run to update them."
)
PEAKS_COMPUTE_FAILED = (
    "The peaks were saved, but the calculations could not be updated. "
    "Select Recompute on the run to update them."
)

_log = structlog.get_logger(__name__)

_Changes = list[tuple[str, str | None, str | None]]  # (field, old, new), as the step reports


def peak_edit_refusal(run: Run) -> str | None:
    """Why the run's melting steps cannot be changed; None when they can.

    Every change recalculates the run, so it is refused exactly when the
    recalculation would be: on a locked run and on an approved one.
    """
    try:
        run.check_recalculation()
    except ConflictError:
        return LOCKED if run.is_locked else NOT_EDITABLE
    return None


def _update_entries(step: MeltingStep, changes: _Changes) -> list[AuditEntry]:
    return [
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


@dataclass(frozen=True, kw_only=True)
class AddMeltingStepCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    well_id: uuid.UUID
    channel_key: str
    value: float
    reason: str | None = None
    assigned_window: str | None = None  # assigns in the same save; the reason serves both


@dataclass(frozen=True, kw_only=True)
class ReviewMeltingStepCommand(Command):
    workspace_id: uuid.UUID
    step_id: uuid.UUID
    expected_version: int
    status: MeltingStepStatus
    value: float
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class AssignMeltingStepCommand(Command):
    workspace_id: uuid.UUID
    step_id: uuid.UUID
    expected_version: int
    window: str | None  # None clears the assignment
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class AcceptMeltingStepsCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    steps: tuple[tuple[uuid.UUID, int], ...]  # (step id, the version the user read)


@dataclass(frozen=True)
class MeltingStepChange:
    step: MeltingStep
    recalculated: bool
    compute_warning: str | None = None


@dataclass(frozen=True)
class MeltingStepsAccepted:
    steps: tuple[MeltingStep, ...]  # the ones that changed, in the order asked
    skipped: int  # already accepted, or rejected: left as they were
    recalculated: bool
    compute_warning: str | None = None


class _StepUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        curve_repo: MeasuredCurveRepository,
        step_repo: MeltingStepRepository,
        audit: AuditRecordingService,
        calculation_engine: ReadoutCalculationEngine,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._curve_repo = curve_repo
        self._step_repo = step_repo
        self._audit = audit
        self._calculation_engine = calculation_engine

    @staticmethod
    def _check_run(run: Run) -> DomainError | None:
        refusal = peak_edit_refusal(run)
        return ConflictError(refusal) if refusal else None

    async def _check_window(self, run: Run, channel_key: str, window: str) -> DomainError | None:
        """A step is assigned only to a current window of the run's protocol on its signal."""
        protocol = await self._protocol_repo.find_by_id_in_workspace(
            run.workspace_id, run.protocol_id
        )
        if protocol is None:
            return NotFoundError("Protocol", str(run.protocol_id))
        on_signal = {
            rd.melt_config.window
            for rd in protocol.readout_definitions
            if rd.melt_config is not None and rd.melt_config.channel_key == channel_key
        }
        if window not in on_signal:
            return ValidationError(f"'{window}' is not a window on this signal")
        return None

    async def _release_window(
        self, step: MeltingStep, by: uuid.UUID
    ) -> list[tuple[MeltingStep, _Changes]]:
        """One step per position and window: clear the others assigned to ``step``'s window.

        Raises ConflictError when one of them changed since it was read.
        """
        released: list[tuple[MeltingStep, _Changes]] = []
        for other in await self._step_repo.find_by_run(step.workspace_id, step.run_id):
            if (
                other.id != step.id
                and other.well_id == step.well_id
                and other.channel_key == step.channel_key
                and other.assigned_window == step.assigned_window
            ):
                read_version = other.version
                changes = other.assign(window=None, reason=None, by=by)
                await self._step_repo.update(other, expected_version=read_version)
                released.append((other, changes))
        return released

    async def _x_range(
        self, ws: uuid.UUID, well_id: uuid.UUID, channel_key: str
    ) -> tuple[float, float] | None:
        curves = await self._curve_repo.find_by_wells(ws, [well_id], channel_key=channel_key)
        curve = next((c for c in curves if c.well_id == well_id), None)
        return (min(curve.x), max(curve.x)) if curve else None

    async def _record(
        self,
        *,
        step: MeltingStep,
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

    async def _record_released(
        self, released: list[tuple[MeltingStep, _Changes]], reason: str | None, user_id: uuid.UUID
    ) -> None:
        for other, changes in released:
            await self._record(
                step=other,
                operation_type=OperationType.PROPERTY_EDIT,
                entries=_update_entries(other, changes),
                reason=reason,
                user_id=user_id,
            )

    async def _save_reviewed(
        self, step: MeltingStep, changes: _Changes, *, expected_version: int, user_id: uuid.UUID
    ) -> None:
        """Write a reviewed step and its audit record.

        Raises ConflictError when the step changed since ``expected_version`` was read.
        """
        await self._step_repo.update(step, expected_version=expected_version)
        await self._record(
            step=step,
            operation_type=OperationType.PROPERTY_EDIT,
            entries=_update_entries(step, changes),
            reason=step.reason,
            user_id=user_id,
        )

    async def _compute(self, run: Run) -> bool:
        """Recalculate the run after a committed change; False when that failed."""
        computed = await self._calculation_engine.compute_for_run(
            run.id, workspace_id=run.workspace_id
        )
        if isinstance(computed, Failure):
            _log.warning(
                "melting_step.compute_failed",
                run_id=str(run.id),
                workspace_id=str(run.workspace_id),
                reason=str(computed.failure()),
            )
            return False
        return True

    async def _recalculate(self, step: MeltingStep, run: Run) -> MeltingStepChange:
        if await self._compute(run):
            return MeltingStepChange(step, True)
        return MeltingStepChange(step, False, COMPUTE_FAILED)


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
            if all(w.id != input.well_id for w in run.wells):
                return Failure(NotFoundError("Position", str(input.well_id)))
            x_range = await self._x_range(ws, input.well_id, input.channel_key)
            if x_range is None:
                return Failure(ValidationError(NO_TRACE))
            if input.assigned_window is not None:
                refused = await self._check_window(run, input.channel_key, input.assigned_window)
                if refused is not None:
                    return Failure(refused)
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
                    assigned_window=input.assigned_window,
                )
            except ValidationError as exc:
                return Failure(exc)
            await self._step_repo.add(step)
            created = [("value", f"{step.value:.15g}"), ("status", step.status.value)]
            released: list[tuple[MeltingStep, _Changes]] = []
            if step.assigned_window is not None:
                created.append(("assigned_window", step.assigned_window))
                try:
                    released = await self._release_window(step, by=user_id)
                except ConflictError as exc:
                    return Failure(exc)
            entries = [
                AuditEntry(
                    entity_type="MeltingStep",
                    entity_id=step.id,
                    field_name=name,
                    action=AuditAction.CREATE,
                    new_value=new,
                )
                for name, new in created
            ]
            await self._record(
                step=step,
                operation_type=OperationType.DATA_ENTRY,
                entries=entries,
                reason=step.reason,
                user_id=user_id,
            )
            await self._record_released(released, step.reason, user_id)
            await self._uow.commit()
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
                await self._save_reviewed(
                    step, changes, expected_version=input.expected_version, user_id=user_id
                )
            except ConflictError as exc:
                return Failure(exc)
            await self._uow.commit()
        return Success(await self._recalculate(step, run))


class AcceptMeltingSteps(_StepUseCase):
    """Accept many unreviewed steps of one run in one save, then recalculate once.

    All or nothing: a step that is not the run's, or one that changed since it was read,
    fails the whole request. Steps already accepted, or rejected, are skipped.
    """

    async def __call__(
        self, input: AcceptMeltingStepsCommand, auth: AuthContext | None = None
    ) -> Result[MeltingStepsAccepted, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id
        user_id = auth.user_id if auth else None
        if user_id is None:
            return Failure(ValidationError("A user is required to accept peaks"))

        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(ws, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            if (refused := self._check_run(run)) is not None:
                return Failure(refused)
            of_run = {s.id: s for s in await self._step_repo.find_by_run(ws, run.id)}
            for step_id, _ in input.steps:
                if step_id not in of_run:
                    return Failure(NotFoundError("MeltingStep", str(step_id)))
            accepted: list[MeltingStep] = []
            try:
                # ponytail: one UPDATE and one audit record per step. A bulk write if a
                # request of the largest size allowed is too slow.
                for step_id, expected_version in input.steps:
                    step = of_run[step_id]
                    if changes := step.accept(by=user_id):
                        await self._save_reviewed(
                            step, changes, expected_version=expected_version, user_id=user_id
                        )
                        accepted.append(step)
            except ConflictError as exc:
                return Failure(exc)  # leaves without a commit: nothing is saved
            skipped = len(input.steps) - len(accepted)
            if not accepted:
                return Success(MeltingStepsAccepted((), skipped, False))
            await self._uow.commit()
        if await self._compute(run):
            return Success(MeltingStepsAccepted(tuple(accepted), skipped, True))
        return Success(MeltingStepsAccepted(tuple(accepted), skipped, False, PEAKS_COMPUTE_FAILED))


class AssignMeltingStep(_StepUseCase):
    """Assign a step to a temperature window, or clear the assignment (``window=None``)."""

    async def __call__(
        self, input: AssignMeltingStepCommand, auth: AuthContext | None = None
    ) -> Result[MeltingStepChange, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id
        user_id = auth.user_id if auth else None
        if user_id is None:
            return Failure(ValidationError("A user is required to assign a peak"))

        async with self._uow:
            step = await self._step_repo.find_by_id(ws, input.step_id)
            if step is None:
                return Failure(NotFoundError("MeltingStep", str(input.step_id)))
            run = await self._run_repo.find_by_id_in_workspace(ws, step.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(step.run_id)))
            if (refused := self._check_run(run)) is not None:
                return Failure(refused)
            if input.window is not None:
                refused = await self._check_window(run, step.channel_key, input.window)
                if refused is not None:
                    return Failure(refused)
            try:
                changes = step.assign(window=input.window, reason=input.reason, by=user_id)
            except ValidationError as exc:
                return Failure(exc)
            released: list[tuple[MeltingStep, _Changes]] = []
            try:
                if changes:
                    await self._step_repo.update(step, expected_version=input.expected_version)
                if step.assigned_window is not None:
                    released = await self._release_window(step, by=user_id)
            except ConflictError as exc:
                return Failure(exc)
            if not changes and not released:
                return Success(MeltingStepChange(step, False))
            # A cleared step keeps no assignment reason, so the audit record carries it.
            reason = (input.reason or "").strip() or None
            if changes:
                await self._record(
                    step=step,
                    operation_type=OperationType.PROPERTY_EDIT,
                    entries=_update_entries(step, changes),
                    reason=reason,
                    user_id=user_id,
                )
            await self._record_released(released, reason, user_id)
            await self._uow.commit()
        return Success(await self._recalculate(step, run))
