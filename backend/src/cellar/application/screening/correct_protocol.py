"""Correct a published protocol's name-feeding facts: one reason, one rename, one audit entry."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.protocol_naming_service import ProtocolNameService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import ProtocolStatus
from cellar.domain.screening_assay.events import ProtocolTargetAdded, ProtocolTargetRemoved
from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.screening_assay.repository import ProtocolRepository, TargetLinkResult
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError
from cellar.domain.shared.events import DomainEvent
from cellar.domain.shared.ontology import OntologyTerm


@dataclass(frozen=True, kw_only=True)
class CorrectProtocolCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    reason: str
    category: str | object | None = UNSET
    discriminator: str | object | None = UNSET
    ontology_annotations: dict[str, list[dict]] | object = UNSET  # slot -> replacement ([] clears)
    target_ids: list[uuid.UUID] | object = UNSET  # the full set of direct targets


class CorrectProtocol:
    """The recorded facts were wrong: fix them in place (same code), with a reason.

    A different experiment is a new protocol, not a correction.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
        *,
        names: ProtocolNameService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._names = names

    async def __call__(
        self, input: CorrectProtocolCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        reason = " ".join(input.reason.split())
        if not reason:
            return Failure(ValidationError("A correction needs a reason"))
        user_id = auth.user_id if auth else None
        link_events: list[DomainEvent] = []
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            if protocol.status != ProtocolStatus.ACTIVE:
                return Failure(
                    ConflictError("Only published protocols are corrected; edit a draft directly")
                )
            if input.category is not UNSET:
                protocol.set_category(input.category, reason=reason)  # type: ignore[arg-type]
            if input.discriminator is not UNSET:
                value = await self._names.clean_discriminator(
                    input.workspace_id,
                    input.discriminator,  # type: ignore[arg-type]
                )
                protocol.set_discriminator(value, reason=reason)
            if input.ontology_annotations is not UNSET:
                for slot, terms in input.ontology_annotations.items():  # type: ignore[union-attr]
                    if terms:
                        protocol.set_ontology_annotation(
                            slot,
                            [
                                OntologyTerm(
                                    term_id=t["term_id"],
                                    label=t["label"],
                                    ontology_source=t["ontology_source"],
                                    uri=t.get("uri"),
                                )
                                for t in terms
                            ],
                            reason=reason,
                        )
                    else:
                        protocol.remove_ontology_annotation(slot, reason=reason)
            if input.target_ids is not UNSET:
                current = set(
                    await self._repo.find_direct_target_ids(input.workspace_id, protocol.id)
                )
                wanted = set(input.target_ids)  # type: ignore[arg-type]
                for target_id in wanted - current:
                    linked = await self._repo.add_direct_target(
                        input.workspace_id, protocol.id, target_id
                    )
                    if linked is TargetLinkResult.TARGET_NOT_FOUND:
                        return Failure(NotFoundError("Target", str(target_id)))
                    link_events.append(
                        ProtocolTargetAdded(
                            aggregate_id=protocol.id,
                            aggregate_type="Protocol",
                            workspace_id=input.workspace_id,
                            target_id=target_id,
                            user_id=user_id,
                        )
                    )
                for target_id in current - wanted:
                    await self._repo.remove_direct_target(
                        input.workspace_id, protocol.id, target_id
                    )
                    link_events.append(
                        ProtocolTargetRemoved(
                            aggregate_id=protocol.id,
                            aggregate_type="Protocol",
                            workspace_id=input.workspace_id,
                            target_id=target_id,
                            user_id=user_id,
                        )
                    )
            # A published name must stay complete: no allow_incomplete here.
            renamed = await self._names.apply(
                protocol,
                reason=f"Correction: {reason}",
                person=True,
                allow_incomplete=False,
                user_id=user_id,
            )
            if isinstance(renamed, Failure):
                return renamed
            await self._repo.save(protocol)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all([*events, *link_events])
        return Success(protocol)
