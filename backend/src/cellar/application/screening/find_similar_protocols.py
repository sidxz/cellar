"""FindSimilarProtocols — surface structurally-similar protocols for a draft.

A read-only query backing the create-time suggestion panel. Suggests; never
blocks. Short-circuits to [] on a blank name so the panel stays quiet until
the user has typed something.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.protocol_similarity import ProtocolSimilarityMatch
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.screening_assay.target import TargetRef
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class FindSimilarProtocolsQuery(Query):
    workspace_id: uuid.UUID
    name: str
    protocol_type: str | None = None
    target_ids: list[uuid.UUID] = field(default_factory=list)
    readout_names: list[str] = field(default_factory=list)
    facet_ids: list[str] = field(default_factory=list)
    limit: int = 5


@dataclass(frozen=True)
class SimilarProtocol:
    match: ProtocolSimilarityMatch
    targets: list[TargetRef] = field(default_factory=list)


class FindSimilarProtocols:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: FindSimilarProtocolsQuery, auth: AuthContext | None = None
    ) -> Result[list[SimilarProtocol], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        if not input.name or not input.name.strip():
            return Success([])
        async with self._uow:
            matches = await self._repo.find_similar(
                input.workspace_id,
                name=input.name.strip(),
                protocol_type=input.protocol_type,
                target_ids=input.target_ids,
                readout_names=input.readout_names,
                facet_ids=input.facet_ids,
                limit=input.limit,
            )
            targets = await self._repo.find_effective_targets_for_protocols(
                input.workspace_id, [m.protocol_id for m in matches]
            )
            return Success(
                [SimilarProtocol(match=m, targets=targets.get(m.protocol_id, [])) for m in matches]
            )
