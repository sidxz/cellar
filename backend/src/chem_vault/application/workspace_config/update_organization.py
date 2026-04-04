"""UpdateOrganization command — partial update of an existing organization."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.command import Command
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError
from chem_vault.domain.workspace_config.enums import OrganizationType
from chem_vault.domain.workspace_config.organization import Organization, _SENTINEL
from chem_vault.domain.workspace_config.repository import OrganizationRepository
from chem_vault.application.shared.unit_of_work import UnitOfWork


@dataclass(frozen=True, kw_only=True)
class UpdateOrganizationCommand(Command):
    workspace_id: uuid.UUID
    org_id: uuid.UUID
    name: str | None = None
    org_type: OrganizationType | None = None
    contact_name: str | None | object = _SENTINEL
    contact_email: str | None | object = _SENTINEL
    notes: str | None | object = _SENTINEL


class UpdateOrganization:
    def __init__(self, uow: UnitOfWork, repo: OrganizationRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: UpdateOrganizationCommand
    ) -> Result[Organization, DomainError]:
        async with self._uow:
            org = await self._repo.find_by_id(input.org_id)
            if org is None or org.workspace_id != input.workspace_id:
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

            org.update(
                name=input.name if input.name is not None else _SENTINEL,
                org_type=input.org_type if input.org_type is not None else _SENTINEL,
                contact_name=input.contact_name,
                contact_email=input.contact_email,
                notes=input.notes,
            )
            await self._repo.save(org)
            await self._uow.commit()
            return Success(org)
