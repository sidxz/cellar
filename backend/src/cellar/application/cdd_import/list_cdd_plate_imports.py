"""ListCddPlateImports query — list CDD plate imports for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.cdd_plate_import import CddPlateImport
from cellar.domain.inventory.repository import CddPlateImportRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListCddPlateImportsQuery(Query):
    workspace_id: uuid.UUID


class ListCddPlateImports:
    """List all CDD plate imports for a workspace, newest first."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: CddPlateImportRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListCddPlateImportsQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[CddPlateImport], DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            imports = await self._repo.find_by_workspace(input.workspace_id)

        return Success(imports)
