"""GetPlateMap query — plate map read model for a screening run."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.screening.plate_map_reader import (
    PlateMapData,
    PlateMapReader,
    PlateMapResult,
    WellMapEntry,
)
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError, NotFoundError

# Re-export so existing imports from this module keep working.
__all__ = [
    "GetPlateMap",
    "GetPlateMapQuery",
    "PlateMapData",
    "PlateMapResult",
    "WellMapEntry",
]


@dataclass(frozen=True, kw_only=True)
class GetPlateMapQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


class GetPlateMap:
    """Return structured plate map data with molecule names and concentrations.

    Delegates raw SA queries to PlateMapReader (infrastructure).
    """

    def __init__(self, reader: PlateMapReader) -> None:
        self._reader = reader

    async def __call__(
        self,
        input: GetPlateMapQuery,
        auth: AuthContext | None = None,
    ) -> Result[PlateMapResult, DomainError]:
        require_same_workspace(auth, input.workspace_id)

        result = await self._reader.get_plate_map(input.workspace_id, input.run_id)
        if result is None:
            return Failure(NotFoundError("Run", str(input.run_id)))

        return Success(result)
