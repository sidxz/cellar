"""References: where a protocol comes from (ChEMBL assay, PubChem AID, DOI, PMID, URL)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.protocol import Protocol, ProtocolReference
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class AddProtocolReferenceCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    kind: str
    value: str


@dataclass(frozen=True, kw_only=True)
class RemoveProtocolReferenceCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    key: str  # <kind>:<value>, as ProtocolReference.key


_Command = AddProtocolReferenceCommand | RemoveProtocolReferenceCommand


class _ReferenceUseCase:
    def __init__(
        self, uow: UnitOfWork, repo: ProtocolRepository, dispatcher: EventDispatcherProtocol
    ) -> None:
        self._uow, self._repo, self._dispatcher = uow, repo, dispatcher

    def _apply(self, protocol: Protocol, input: _Command) -> None:
        raise NotImplementedError

    async def __call__(
        self, input: _Command, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            self._apply(protocol, input)
            await self._repo.save(protocol)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(protocol)


class AddProtocolReference(_ReferenceUseCase):
    def _apply(self, protocol: Protocol, input: _Command) -> None:
        assert isinstance(input, AddProtocolReferenceCommand)
        protocol.add_reference(ProtocolReference(kind=input.kind, value=input.value))  # type: ignore[arg-type]


class RemoveProtocolReference(_ReferenceUseCase):
    def _apply(self, protocol: Protocol, input: _Command) -> None:
        assert isinstance(input, RemoveProtocolReferenceCommand)
        protocol.remove_reference(input.key)
