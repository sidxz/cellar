"""ImportTemplate use cases — CRUD for saved column mappings."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.import_template import ImportTemplate
from chem_vault.domain.inventory.repository import ImportTemplateRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class CreateImportTemplateCommand(Command):
    workspace_id: uuid.UUID
    name: str
    column_mappings: dict
    description: str | None = None
    default_protocol_id: uuid.UUID | None = None
    created_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListImportTemplatesQuery(Query):
    workspace_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class DeleteImportTemplateCommand(Command):
    workspace_id: uuid.UUID
    template_id: uuid.UUID


class CreateImportTemplate:
    def __init__(self, uow: UnitOfWork, repo: ImportTemplateRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: CreateImportTemplateCommand, auth: AuthContext | None = None
    ) -> Result[ImportTemplate, DomainError]:
        require_editor(auth)
        async with self._uow:
            template = ImportTemplate.create(
                workspace_id=input.workspace_id,
                name=input.name,
                column_mappings=input.column_mappings,
                description=input.description,
                default_protocol_id=input.default_protocol_id,
                created_by=input.created_by,
            )
            await self._repo.save(template)
            await self._uow.commit()
            return Success(template)


class ListImportTemplates:
    def __init__(self, uow: UnitOfWork, repo: ImportTemplateRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListImportTemplatesQuery
    ) -> Result[list[ImportTemplate], DomainError]:
        async with self._uow:
            templates = await self._repo.find_by_workspace(input.workspace_id)
            return Success(templates)


class DeleteImportTemplate:
    def __init__(self, uow: UnitOfWork, repo: ImportTemplateRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: DeleteImportTemplateCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        async with self._uow:
            template = await self._repo.find_by_id(input.template_id)
            if template is None or template.workspace_id != input.workspace_id:
                return Failure(NotFoundError("ImportTemplate", str(input.template_id)))
            await self._repo.delete(input.workspace_id, input.template_id)
            await self._uow.commit()
            return Success(None)
