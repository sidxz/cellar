"""GetCurveFittedLayers — the layer each dose-response readout's curves are fitted on.

Routes that return curves (by id, after a refit or a class change) read it here so every
curve payload names its layer, resolved from the protocol by the rule the fit uses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening._response_scale import curve_fitted_layer
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import DomainError

# (protocol_id, readout_definition_id) of a dose-response readout
ReadoutKey = tuple[uuid.UUID, uuid.UUID]


@dataclass(frozen=True, kw_only=True)
class GetCurveFittedLayersQuery(Query):
    workspace_id: uuid.UUID
    readouts: frozenset[ReadoutKey]


class GetCurveFittedLayers:
    def __init__(self, *, uow: UnitOfWork, protocol_repo: ProtocolRepository) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo

    async def __call__(
        self, input: GetCurveFittedLayersQuery, auth: AuthContext | None = None
    ) -> Result[dict[ReadoutKey, str | None], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        if not input.readouts:
            return Success({})
        async with self._uow:
            protocols = await self._protocol_repo.find_by_ids(
                input.workspace_id, list({p for p, _ in input.readouts})
            )
        by_id = {p.id: p for p in protocols}
        return Success({(p, rd): curve_fitted_layer(by_id.get(p), rd) for p, rd in input.readouts})
