"""UpdateMolecule command — update mutable fields (tags, lifecycle, custom_fields)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.pipeline import is_successful
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.workspace_config.custom_field_validator import CustomFieldValidator
from cellar.domain.chemical_registration.enums import LifecycleStage
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.workspace_config.enums import FieldTarget


@dataclass(frozen=True, kw_only=True)
class UpdateMoleculeCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    # Lifecycle
    lifecycle_stage: str | None = None
    lifecycle_reason: str | None = None
    # Custom fields
    custom_fields: dict | None = field(default=UNSET)  # type: ignore[assignment]
    # Actor
    changed_by: uuid.UUID


class UpdateMolecule:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
        custom_field_validator: CustomFieldValidator | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._custom_field_validator = custom_field_validator

    async def __call__(
        self,
        input: UpdateMoleculeCommand,
        auth: AuthContext | None = None,
    ) -> Result[Molecule, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            mol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            try:
                if input.lifecycle_stage is not None:
                    try:
                        stage = LifecycleStage(input.lifecycle_stage)
                    except ValueError:
                        return Failure(
                            ValidationError(
                                f"Invalid lifecycle_stage '{input.lifecycle_stage}'. "
                                f"Allowed: {[s.value for s in LifecycleStage]}"
                            )
                        )
                    mol.advance_lifecycle(
                        stage,
                        changed_by=input.changed_by,
                        reason=input.lifecycle_reason,
                    )

                if input.custom_fields is not UNSET:
                    if self._custom_field_validator and input.custom_fields is not None:
                        validation = await self._custom_field_validator.validate(
                            input.custom_fields, FieldTarget.MOLECULE, input.workspace_id
                        )
                        if not is_successful(validation):
                            return Failure(validation.failure())
                    mol.update_custom_fields(
                        input.custom_fields if input.custom_fields is not None else {}
                    )
            except ValidationError as exc:
                return Failure(exc)

            await self._repo.save(mol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(mol)
