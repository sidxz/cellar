"""CreateOrganization command — register a new organization in a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.command import Command
from chem_vault.domain.shared.errors import ConflictError, DomainError
from chem_vault.domain.workspace_config.enums import OrganizationType
from chem_vault.domain.workspace_config.organization import Organization
from chem_vault.domain.workspace_config.repository import OrganizationRepository
from chem_vault.application.shared.unit_of_work import UnitOfWork


@dataclass(frozen=True, kw_only=True)
class CreateOrganizationCommand(Command):
    workspace_id: uuid.UUID
    name: str
    org_type: OrganizationType
    contact_name: str | None = None
    contact_email: str | None = None
    notes: str | None = None


class CreateOrganization:
    def __init__(self, uow: UnitOfWork, repo: OrganizationRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: CreateOrganizationCommand
    ) -> Result[Organization, DomainError]:
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
            await self._uow.commit()
            return Success(org)
