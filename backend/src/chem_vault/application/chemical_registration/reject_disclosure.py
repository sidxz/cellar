"""RejectDisclosure — reject a disclosure that is awaiting merge confirmation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.disclosure_request import DisclosureRequest
from chem_vault.domain.chemical_registration.enums import DisclosureStatus
from chem_vault.domain.chemical_registration.repository import (
    DisclosureRequestRepository,
)
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class RejectDisclosureCommand(Command):
    workspace_id: uuid.UUID
    disclosure_id: uuid.UUID
    reason: str | None = None
    rejected_by: uuid.UUID


class RejectDisclosure:
    """Reject a disclosure in PENDING_CONFIRMATION status.

    The source molecule stays undisclosed.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        disclosure_repo: DisclosureRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._disclosure_repo = disclosure_repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: RejectDisclosureCommand,
        auth: AuthContext | None = None,
    ) -> Result[DisclosureRequest, DomainError]:
        require_editor(auth)

        async with self._uow:
            dr = await self._disclosure_repo.find_by_id_in_workspace(
                input.workspace_id, input.disclosure_id
            )
            if dr is None:
                return Failure(
                    NotFoundError("DisclosureRequest", str(input.disclosure_id))
                )

            if dr.status != DisclosureStatus.PENDING_CONFIRMATION:
                return Failure(
                    ValidationError(
                        f"Disclosure is in '{dr.status.value}' status, "
                        f"not 'pending_confirmation'"
                    )
                )

            dr.reject(reason=input.reason or "Merge rejected by user")

            await self._disclosure_repo.save(dr)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

            return Success(dr)
