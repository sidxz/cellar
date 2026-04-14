"""ListCddMoleculeImports query — list CDD molecule imports for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.cdd_molecule_import import CddMoleculeImport
from chem_vault.domain.chemical_registration.repository import CddMoleculeImportRepository
from chem_vault.domain.shared.errors import DomainError


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

        async with self._uow:
            imports = await self._repo.find_by_workspace(input.workspace_id)

        return Success(imports)
