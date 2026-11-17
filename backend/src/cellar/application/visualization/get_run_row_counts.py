"""GetRunRowCounts — rows each run of a protocol adds to a Wells dataset (run picker)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.shared.query import Query
from cellar.application.visualization.dataset_reader import VisualizationDatasetReader
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetRunRowCountsQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


class GetRunRowCounts:
    def __init__(self, reader: VisualizationDatasetReader) -> None:
        self._reader = reader

    async def __call__(
        self, input: GetRunRowCountsQuery, auth: AuthContext | None = None
    ) -> Result[dict[uuid.UUID, int], DomainError]:
        require_same_workspace(auth, input.workspace_id)
        runs = await self._reader.runs_for_protocol(input.workspace_id, input.protocol_id)
        if runs is None:
            return Failure(NotFoundError("Protocol", str(input.protocol_id)))
        counts = await self._reader.count_wells_rows(input.workspace_id, [r.id for r in runs])
        return Success({r.id: counts.get(r.id, 0) for r in runs})
