"""Manage ontology annotations on protocols — Set and Remove."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.protocol import Protocol
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.domain.shared.ontology import OntologyTerm


@dataclass(frozen=True, kw_only=True)
class SetOntologyAnnotationCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    slot: str
    terms: list[dict] = field(default_factory=list)  # [{term_id, label, ontology_source, uri?}]


class SetOntologyAnnotation:
    """Set ontology terms for a slot on a DRAFT protocol."""

    def __init__(
        self,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: SetOntologyAnnotationCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)

        async with self._uow:
            protocol = await self._protocol_repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            terms = [
                OntologyTerm(
                    term_id=t["term_id"],
                    label=t["label"],
                    ontology_source=t["ontology_source"],
                    uri=t.get("uri"),
                )
                for t in input.terms
            ]
            protocol.set_ontology_annotation(input.slot, terms)

            await self._protocol_repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)


@dataclass(frozen=True, kw_only=True)
class RemoveOntologyAnnotationCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    slot: str


class RemoveOntologyAnnotation:
    """Remove all ontology terms for a slot from a DRAFT protocol."""

    def __init__(
        self,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RemoveOntologyAnnotationCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)

        async with self._uow:
            protocol = await self._protocol_repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            protocol.remove_ontology_annotation(input.slot)

            await self._protocol_repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)
