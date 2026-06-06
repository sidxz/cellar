"""ListCddMoleculeImports query — list CDD molecule imports for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.cdd_molecule_import import CddMoleculeImport
from cellar.domain.chemical_registration.repository import CddMoleculeImportRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListCddMoleculeImportsQuery(Query):
    workspace_id: uuid.UUID


class ListCddMoleculeImports:
    """List all CDD molecule imports for a workspace, newest first."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: CddMoleculeImportRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListCddMoleculeImportsQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[CddMoleculeImport], DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            imports = await self._repo.find_by_workspace(input.workspace_id)

        return Success(imports)
