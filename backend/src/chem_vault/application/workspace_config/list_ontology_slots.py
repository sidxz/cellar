"""ListOntologySlots query — list ontology slot definitions for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_workspace_role
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.workspace_config.ontology_slot_definition import OntologySlotDefinition
from chem_vault.domain.workspace_config.repository import OntologySlotDefinitionRepository


@dataclass(frozen=True, kw_only=True)
class ListOntologySlotsQuery(Query):
    workspace_id: uuid.UUID


class ListOntologySlots:
    def __init__(self, uow: UnitOfWork, repo: OntologySlotDefinitionRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListOntologySlotsQuery, auth: AuthContext | None = None
    ) -> Result[list[OntologySlotDefinition], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            results = await self._repo.find_by_workspace(input.workspace_id)
            return Success(results)
