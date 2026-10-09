"""Common units for the unit picker. Free text stays allowed; this is only a suggestion list."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError
from cellar.domain.shared.units import COMMON_UNITS, UnitSuggestion


@dataclass(frozen=True, kw_only=True)
class ListUnitsQuery(Query):
    workspace_id: uuid.UUID


class ListUnits:
    async def __call__(
        self, input: ListUnitsQuery, auth: AuthContext | None = None
    ) -> Result[list[UnitSuggestion], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        return Success(list(COMMON_UNITS))
