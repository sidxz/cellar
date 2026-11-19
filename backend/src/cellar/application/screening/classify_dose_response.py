"""ClassifyDoseResponseCurve — override the auto-assigned curve class.

The class decides how every reader reports the curve ("> highest dose" for inactive,
"< lowest dose" for active at all doses), so each change is recorded in the curve's audit
trail: who, when, and the class before and after.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.audit_compliance.enums import AuditAction, OperationType
from cellar.domain.audit_compliance.models import AuditEntry
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveClass
from cellar.domain.screening_assay.repository import DoseResponseCurveRepository
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class ClassifyDoseResponseCurveCommand(Command):
    workspace_id: uuid.UUID
    curve_id: uuid.UUID
    curve_class: str


class ClassifyDoseResponseCurve:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        curve_repo: DoseResponseCurveRepository,
        audit: AuditRecordingService,
    ) -> None:
        self._uow = uow
        self._curve_repo = curve_repo
        self._audit = audit

    async def __call__(
        self, input: ClassifyDoseResponseCurveCommand, auth: AuthContext | None = None
    ) -> Result[DoseResponseCurve, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        assert auth is not None  # require_authenticated
        try:
            new_class = CurveClass(input.curve_class)
        except ValueError:
            known = ", ".join(c.value for c in CurveClass)
            return Failure(
                ValidationError(f"Unknown curve class {input.curve_class!r} (one of {known})")
            )

        async with self._uow:
            curve = await self._curve_repo.find_by_id_in_workspace(
                input.workspace_id, input.curve_id
            )
            if curve is None:
                return Failure(NotFoundError("DoseResponseCurve", str(input.curve_id)))

            old_class = curve.curve_class
            curve.curve_class = new_class
            await self._curve_repo.save(curve)
            # In the same transaction: the class change and its record commit together.
            await self._audit.record(
                workspace_id=input.workspace_id,
                operation_type=OperationType.PROPERTY_EDIT,
                entity_type="DoseResponseCurve",
                entity_id=curve.id,
                user_id=auth.user_id,
                entries=[
                    AuditEntry(
                        entity_type="DoseResponseCurve",
                        entity_id=curve.id,
                        field_name="curve_class",
                        action=AuditAction.UPDATE,
                        old_value=old_class.value if old_class is not None else None,
                        new_value=new_class.value,
                    )
                ],
                session=self._uow.session,
            )
            await self._uow.commit()
            return Success(curve)
