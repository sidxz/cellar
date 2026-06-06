"""CreateOrganization command — register a new organization in a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import ConflictError, DomainError
from cellar.domain.workspace_config.enums import OrganizationType
from cellar.domain.workspace_config.organization import Organization
from cellar.domain.workspace_config.repository import OrganizationRepository


@dataclass(frozen=True, kw_only=True)
class CreateOrganizationCommand(Command):
    workspace_id: uuid.UUID
    name: str
    org_type: OrganizationType
    contact_name: str | None = None
    contact_email: str | None = None
    notes: str | None = None


class CreateOrganization:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: OrganizationRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateOrganizationCommand, auth: AuthContext | None = None
    ) -> Result[Organization, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            existing = await self._repo.find_by_name(input.workspace_id, input.name.strip())
            if existing is not None:
                return Failure(
                    ConflictError(f"Organization '{input.name.strip()}' already exists")
                )

            org = Organization.create(
                workspace_id=input.workspace_id,
                name=input.name,
                org_type=input.org_type,
                contact_name=input.contact_name,
                contact_email=input.contact_email,
                notes=input.notes,
            )
            await self._repo.save(org)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(org)
