"""ListOntologySlots query — list ontology slot definitions for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.ontology_slot_definition import OntologySlotDefinition
from cellar.domain.workspace_config.repository import OntologySlotDefinitionRepository


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
