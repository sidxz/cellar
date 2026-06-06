"""ListRelationships query — retrieve all relationships for a molecule."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from cellar.domain.chemical_registration.repository import (
    MoleculeRelationshipRepository,
    MoleculeRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ListRelationshipsQuery(Query):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


class ListRelationships:
    """Query use case: list all relationships where molecule is source or target."""

    def __init__(
        self,
        uow: UnitOfWork,
        molecule_repo: MoleculeRepository,
        relationship_repo: MoleculeRelationshipRepository,
    ) -> None:
        self._uow = uow
        self._molecule_repo = molecule_repo
        self._relationship_repo = relationship_repo

    async def __call__(
        self, input: ListRelationshipsQuery, auth: AuthContext | None = None
    ) -> Result[list[MoleculeRelationship], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            # Workspace isolation
            mol = await self._molecule_repo.find_by_id_in_workspace(
                input.workspace_id, input.molecule_id
            )
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            as_source = await self._relationship_repo.find_by_source(
                input.workspace_id, input.molecule_id
            )
            as_target = await self._relationship_repo.find_by_target(
                input.workspace_id, input.molecule_id
            )

            # Deduplicate (shouldn't overlap, but safe)
            seen = set()
            combined = []
            for rel in as_source + as_target:
                if rel.id not in seen:
                    seen.add(rel.id)
                    combined.append(rel)

            return Success(combined)
