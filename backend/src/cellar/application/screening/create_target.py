"""CreateTarget use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.screening_assay.repository import TargetRepository
from cellar.domain.screening_assay.target import Target
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class CreateTargetCommand(Command):
    workspace_id: uuid.UUID
    name: str
    target_type: str
    organism: str | None = None
    gene_name: str | None = None
    uniprot_id: str | None = None
    ncbi_gene_id: str | None = None
    description: str | None = None
    target_class: str | None = None
    sequence: str | None = None


class CreateTarget:
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
        self, input: CreateTargetCommand, auth: AuthContext | None = None
    ) -> Result[Target, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            target = Target.create(
                workspace_id=input.workspace_id,
                name=input.name,
                target_type=TargetType(input.target_type),
                organism=input.organism,
                gene_name=input.gene_name,
                uniprot_id=input.uniprot_id,
                ncbi_gene_id=input.ncbi_gene_id,
                description=input.description,
                target_class=input.target_class,
                sequence=input.sequence,
            )
            await self._repo.save(target)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(target)
