"""Manage ontology annotations on protocols — Set and Remove."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.manage_protocol import correction_reason
from cellar.application.screening.protocol_naming_service import ProtocolNameService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import ProtocolStatus
from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.shared.ontology import OntologyTerm

# Audit reasons for renames caused by an annotation change.
SLOT_LABELS = {
    "organism": "Organism",
    "strain": "Strain",
    "cell_line": "Cell line",
    "assay_format": "Assay format",
    "detection": "Detection method",
}


@dataclass(frozen=True, kw_only=True)
class SetOntologyAnnotationCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    slot: str
    terms: list[dict] = field(default_factory=list)  # [{term_id, label, ontology_source, uri?}]
    reason: str | None = None  # required to correct a published protocol


class SetOntologyAnnotation:
    """Set ontology terms for a slot on a DRAFT protocol."""

    def __init__(
        self,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
        *,
        names: ProtocolNameService,
    ) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._dispatcher = dispatcher
        self._names = names

    async def __call__(
        self, input: SetOntologyAnnotationCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

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
            protocol.set_ontology_annotation(input.slot, terms, reason=input.reason)

            renamed = await self._names.apply(
                protocol,
                reason=correction_reason(
                    input.reason, f"{SLOT_LABELS.get(input.slot, input.slot)} changed"
                ),
                person=True,
                # A draft may be incomplete for a while; a published name must stay complete.
                allow_incomplete=protocol.status != ProtocolStatus.ACTIVE,
                user_id=auth.user_id if auth else None,
            )
            if isinstance(renamed, Failure):
                return renamed

            await self._protocol_repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)


@dataclass(frozen=True, kw_only=True)
class RemoveOntologyAnnotationCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    slot: str
    reason: str | None = None  # required to correct a published protocol


class RemoveOntologyAnnotation:
    """Remove all ontology terms for a slot from a DRAFT protocol."""

    def __init__(
        self,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
        *,
        names: ProtocolNameService,
    ) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._dispatcher = dispatcher
        self._names = names

    async def __call__(
        self, input: RemoveOntologyAnnotationCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            protocol = await self._protocol_repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            protocol.remove_ontology_annotation(input.slot, reason=input.reason)

            renamed = await self._names.apply(
                protocol,
                reason=correction_reason(
                    input.reason, f"{SLOT_LABELS.get(input.slot, input.slot)} changed"
                ),
                person=True,
                # A draft may be incomplete for a while; a published name must stay complete.
                allow_incomplete=protocol.status != ProtocolStatus.ACTIVE,
                user_id=auth.user_id if auth else None,
            )
            if isinstance(renamed, Failure):
                return renamed

            await self._protocol_repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)
