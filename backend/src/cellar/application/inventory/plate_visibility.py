"""PlateVisibilityService — private-org plate exclusion for list/get."""

from __future__ import annotations

import uuid

from cellar.application.auth import AuthContext
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.repository import OrgPlatePolicyRepository


class PlateVisibilityService:
    """S2 scope: private-org exclusion. The 'plates on active loan to my org
    stay visible' clause lands in S4 with PlateLoan — extend excluded_org_ids
    callers there, not here."""

    def __init__(self, policy_repo: OrgPlatePolicyRepository) -> None:
        self._policy_repo = policy_repo

    async def excluded_org_ids(
        self, workspace_id: uuid.UUID, auth: AuthContext | None
    ) -> set[uuid.UUID]:
        """Private org ids, minus the caller's own org. Empty for system calls."""
        if auth is None:
            return set()
        private_org_ids = await self._policy_repo.list_private_org_ids(workspace_id)
        return private_org_ids - {auth.org_id}

    def can_view(
        self, plate: RegisteredPlate, auth: AuthContext | None, excluded: set[uuid.UUID]
    ) -> bool:
        """False iff plate.owner_org_id in excluded."""
        return plate.owner_org_id not in excluded
