"""GetPlateInsights — org-scoped dashboard counts behind the S2 privacy gate."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.inventory.plate_insights_reader import (
    PlateInsightsData,
    PlateInsightsReader,
)
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import AuthorizationError, DomainError, ValidationError


@dataclass(frozen=True, kw_only=True)
class GetPlateInsightsQuery(Query):
    workspace_id: uuid.UUID
    org_id: uuid.UUID | None = None


class GetPlateInsights:
    """Org-scoped plate/loan insight counts for the dashboard (spec §9, §11).

    Org defaulting + the private-org gate mirror ``GetGroupTree`` exactly
    (plate_groups.py): ``org_id`` defaults to the caller's own org, and a
    private foreign org 403s for non-members. The reader opens its own
    session AFTER the gate passes — it isn't uow-bound.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        visibility: PlateVisibilityService,
        reader: PlateInsightsReader,
    ) -> None:
        self._uow = uow
        self._visibility = visibility
        self._reader = reader

    async def __call__(
        self, input: GetPlateInsightsQuery, auth: AuthContext | None = None
    ) -> Result[tuple[uuid.UUID, PlateInsightsData], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        org_id = input.org_id if input.org_id is not None else (auth.org_id if auth else None)
        if org_id is None:
            return Failure(ValidationError("org_id is required (caller has no organization)"))

        async with self._uow:
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if org_id in excluded:
                # Spec §5: org-scoped reads of a private org are member-only.
                raise AuthorizationError("This organization's plates are private")

        data = await self._reader.get_insights(input.workspace_id, org_id)
        return Success((org_id, data))
