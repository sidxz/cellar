"""CreateDoseResponseCurve use case with DataLockGuard protection."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.data_lock_guard import DataLockGuard
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.enums import CurveClass, CurveType
from chem_vault.domain.screening_assay.repository import DoseResponseCurveRepository, RunRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class CreateDoseResponseCurveCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    batch_id: uuid.UUID
    protocol_id: uuid.UUID
    run_id: uuid.UUID
    curve_type: str
    fitted_value: float
    fitted_unit: str
    hill_slope: float
    top: float
    bottom: float
    r_squared: float
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    num_points: int
    curve_class: str | None = None
    raw_data: list[dict[str, Any]] = field(default_factory=list)
    excluded_points: list[dict[str, Any]] | None = None


class CreateDoseResponseCurve:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: DoseResponseCurveRepository,
        guard: DataLockGuard,
        dispatcher: EventDispatcherProtocol,
        run_repo: RunRepository | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._guard = guard
        self._dispatcher = dispatcher
        self._run_repo = run_repo

    async def __call__(
        self, input: CreateDoseResponseCurveCommand, auth: AuthContext | None = None
    ) -> Result[DoseResponseCurve, DomainError]:
        require_editor(auth)

        async with self._uow:
            # Verify run belongs to this workspace
            if self._run_repo is not None:
                run = await self._run_repo.find_by_id_in_workspace(
                    input.workspace_id, input.run_id
                )
                if run is None:
                    return Failure(NotFoundError("Run", str(input.run_id)))

            # Guard against locked runs
            try:
                await self._guard.guard_write(input.workspace_id, input.run_id)
            except DomainError as exc:
                return Failure(exc)

            curve = DoseResponseCurve(
                workspace_id=input.workspace_id,
                molecule_id=input.molecule_id,
                batch_id=input.batch_id,
                protocol_id=input.protocol_id,
                run_id=input.run_id,
                curve_type=CurveType(input.curve_type),
                fitted_value=input.fitted_value,
                fitted_unit=input.fitted_unit,
                hill_slope=input.hill_slope,
                top=input.top,
                bottom=input.bottom,
                r_squared=input.r_squared,
                confidence_interval_low=input.confidence_interval_low,
                confidence_interval_high=input.confidence_interval_high,
                num_points=input.num_points,
                curve_class=CurveClass(input.curve_class) if input.curve_class else None,
                raw_data=input.raw_data or None,
                excluded_points=input.excluded_points,
            )
            await self._repo.save(curve)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(curve)
