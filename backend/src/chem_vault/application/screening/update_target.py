"""UpdateTarget command — partial update of an existing target."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.enums import TargetType
from chem_vault.domain.screening_assay.repository import TargetRepository
from chem_vault.domain.screening_assay.target import Target
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class UpdateTargetCommand(Command):
    workspace_id: uuid.UUID
    target_id: uuid.UUID
    name: str | None = None
    target_type: str | None = None
    organism: str | None | object = UNSET
    gene_name: str | None | object = UNSET
    uniprot_id: str | None | object = UNSET
    ncbi_gene_id: str | None | object = UNSET
    description: str | None | object = UNSET
    target_class: str | None | object = UNSET
    sequence: str | None | object = UNSET


class UpdateTarget:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: TargetRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdateTargetCommand, auth: AuthContext | None = None
    ) -> Result[Target, DomainError]:
        require_editor(auth)

        async with self._uow:
            target = await self._repo.find_by_id_in_workspace(input.workspace_id, input.target_id)
            if target is None:
                return Failure(NotFoundError("Target", str(input.target_id)))

            fields: dict[str, Any] = {}
            if input.name is not None:
                fields["name"] = input.name
            if input.target_type is not None:
                fields["target_type"] = TargetType(input.target_type)
            if input.organism is not UNSET:
                fields["organism"] = input.organism
            if input.gene_name is not UNSET:
                fields["gene_name"] = input.gene_name
            if input.uniprot_id is not UNSET:
                fields["uniprot_id"] = input.uniprot_id
            if input.ncbi_gene_id is not UNSET:
                fields["ncbi_gene_id"] = input.ncbi_gene_id
            if input.description is not UNSET:
                fields["description"] = input.description
            if input.target_class is not UNSET:
                fields["target_class"] = input.target_class
            if input.sequence is not UNSET:
                fields["sequence"] = input.sequence

            if fields:
                target.update(**fields)
            await self._repo.save(target)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(target)
