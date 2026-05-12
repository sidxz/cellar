"""ClassifyDoseResponseCurve — override the auto-assigned curve class."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveClass
from cellar.domain.screening_assay.repository import DoseResponseCurveRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ClassifyDoseResponseCurveCommand(Command):
    workspace_id: uuid.UUID
    curve_id: uuid.UUID
    curve_class: str


class ClassifyDoseResponseCurve:
    def __init__(self, *, uow: UnitOfWork, curve_repo: DoseResponseCurveRepository) -> None:
        self._uow = uow
        self._curve_repo = curve_repo

    async def __call__(
        self, input: ClassifyDoseResponseCurveCommand, auth: AuthContext | None = None
    ) -> Result[DoseResponseCurve, DomainError]:
        require_editor(auth)

        async with self._uow:
            curve = await self._curve_repo.find_by_id_in_workspace(
                input.workspace_id, input.curve_id
            )
            if curve is None:
                return Failure(NotFoundError("DoseResponseCurve", str(input.curve_id)))

            curve.curve_class = CurveClass(input.curve_class)
            await self._curve_repo.save(curve)
            await self._uow.commit()
            return Success(curve)
