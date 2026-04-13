"""UpdateOrganization command — partial update of an existing organization."""

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
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError
from chem_vault.domain.workspace_config.enums import OrganizationType
from chem_vault.domain.workspace_config.organization import Organization
from chem_vault.domain.workspace_config.repository import OrganizationRepository


@dataclass(frozen=True, kw_only=True)
class UpdateOrganizationCommand(Command):
    workspace_id: uuid.UUID
    org_id: uuid.UUID
    name: str | None = None
    org_type: OrganizationType | None = None
    contact_name: str | None | object = UNSET
    contact_email: str | None | object = UNSET
    notes: str | None | object = UNSET


class UpdateOrganization:
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
        self, input: UpdateOrganizationCommand, auth: AuthContext | None = None
    ) -> Result[Organization, DomainError]:
        require_editor(auth)

        async with self._uow:
            org = await self._repo.find_by_id_in_workspace(input.workspace_id, input.org_id)
            if org is None:
                return Failure(NotFoundError("Organization", str(input.org_id)))

            # Name uniqueness check
            if input.name is not None:
                existing = await self._repo.find_by_name(
                    input.workspace_id, input.name.strip()
                )
                if existing is not None and existing.id != org.id:
                    return Failure(
                        ConflictError(f"Organization '{input.name.strip()}' already exists")
                    )

            # Build kwargs dict — only include fields that were provided
            fields: dict[str, Any] = {}
            if input.name is not None:
                fields["name"] = input.name
            if input.org_type is not None:
                fields["org_type"] = input.org_type
            if input.contact_name is not UNSET:
                fields["contact_name"] = input.contact_name
            if input.contact_email is not UNSET:
                fields["contact_email"] = input.contact_email
            if input.notes is not UNSET:
                fields["notes"] = input.notes

            if fields:
                org.update(**fields)
            await self._repo.save(org)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(org)
