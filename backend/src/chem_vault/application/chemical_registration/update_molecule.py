"""UpdateMolecule command — update mutable fields (tags, lifecycle, custom_fields)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.enums import LifecycleStage
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class UpdateMoleculeCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    # Tags
    add_tags: list[str] | None = None
    remove_tags: list[str] | None = None
    # Lifecycle
    lifecycle_stage: str | None = None
    lifecycle_reason: str | None = None
    # Custom fields
    custom_fields: dict | None = field(default=UNSET)  # type: ignore[assignment]
    # Actor
    changed_by: uuid.UUID = field(default_factory=uuid.uuid4)


class UpdateMolecule:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: UpdateMoleculeCommand,
        auth: AuthContext | None = None,
    ) -> Result[Molecule, DomainError]:
        require_editor(auth)

        async with self._uow:
            mol = await self._repo.find_by_id(input.molecule_id)
            if mol is None or mol.workspace_id != input.workspace_id:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            try:
                if input.add_tags or input.remove_tags:
                    mol.update_tags(added=input.add_tags, removed=input.remove_tags)

                if input.lifecycle_stage is not None:
                    mol.advance_lifecycle(
                        LifecycleStage(input.lifecycle_stage),
                        changed_by=input.changed_by,
                        reason=input.lifecycle_reason,
                    )

                if input.custom_fields is not UNSET:
                    mol.update_custom_fields(input.custom_fields)  # type: ignore[arg-type]
            except ValidationError as exc:
                return Failure(exc)

            await self._repo.save(mol)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(mol)
