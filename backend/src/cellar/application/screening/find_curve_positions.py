"""FindCurvePositions query: the positions of a protocol that have measured curves."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening.curve_position_reader import (
    CurvePositionReader,
    CurvePositions,
)
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError

MAX_CURVE_RUNS = 8
MAX_CURVE_MOLECULES = 50


@dataclass(frozen=True, kw_only=True)
class FindCurvePositionsQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    run_ids: tuple[uuid.UUID, ...] = ()
    molecule_ids: tuple[uuid.UUID, ...] = ()


class FindCurvePositions:
    """List a protocol's runs with curves and the positions matching the filters.

    No unit of work: the reader is a read model that opens its own session
    (precedent ``GetPlateMap``).
    """

    def __init__(self, reader: CurvePositionReader) -> None:
        self._reader = reader

    async def __call__(
        self, input: FindCurvePositionsQuery, auth: AuthContext | None = None
    ) -> Result[CurvePositions, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        if len(input.run_ids) > MAX_CURVE_RUNS:
            return Failure(ValidationError(f"At most {MAX_CURVE_RUNS} runs can be shown at once"))
        if len(input.molecule_ids) > MAX_CURVE_MOLECULES:
            return Failure(
                ValidationError(f"At most {MAX_CURVE_MOLECULES} compounds can be shown at once")
            )

        found = await self._reader.find(
            input.workspace_id,
            input.protocol_id,
            run_ids=input.run_ids,
            molecule_ids=input.molecule_ids,
        )
        if found is None:
            return Failure(NotFoundError("Protocol", str(input.protocol_id)))
        return Success(found)
