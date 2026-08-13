"""PlateVisibilityService — private-org plate exclusion for list/get, plus the
borrowed-plate read carve-out (spec §5 loan clause)."""

from __future__ import annotations

import uuid

from cellar.application.auth import AuthContext
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.repository import OrgPlatePolicyRepository, PlateLoanRepository


class PlateVisibilityService:
    """S2 scope: private-org exclusion. RESOLVED (S4): the 'plates on active
    loan to my org stay visible' clause (spec §5) lives here, via
    ``borrowed_plate_ids`` feeding the ``can_view`` ``borrowed`` param — the
    S2 seam note that pointed callers elsewhere is obsolete now that
    PlateLoanRepository exists.

    Write-path narrowing is deliberate: Update/MapWells/ChangeStatus/Derive/
    Delete, export, tag verbs, and plate groups never fetch a borrowed set
    and call ``can_view``/``can_view_owner`` with their default (empty), so a
    borrower can SEE a loaned plate but not modify it. Only the read surfaces
    — GetPlate, ListPlates, ListChildren, molecule->plates read model — pass
    a real one.
    """

    def __init__(
        self,
        policy_repo: OrgPlatePolicyRepository,
        loan_repo: PlateLoanRepository | None = None,
    ) -> None:
        self._policy_repo = policy_repo
        self._loan_repo = loan_repo

    async def excluded_org_ids(
        self, workspace_id: uuid.UUID, auth: AuthContext | None
    ) -> set[uuid.UUID]:
        """Private org ids, minus the caller's own org. Empty for system calls."""
        if auth is None:
            return set()
        private_org_ids = await self._policy_repo.list_private_org_ids(workspace_id)
        return private_org_ids - {auth.org_id}

    async def borrowed_plate_ids(
        self, workspace_id: uuid.UUID, auth: AuthContext | None
    ) -> set[uuid.UUID]:
        """Plates currently on active loan to the caller's own org (spec §5).
        Empty when there's no loan repo wired, no caller, or the caller has
        no org — system calls never re-admit anything this way."""
        if self._loan_repo is None or auth is None or auth.org_id is None:
            return set()
        return await self._loan_repo.borrowed_plate_ids(workspace_id, auth.org_id)

    def can_view(
        self,
        plate: RegisteredPlate,
        auth: AuthContext | None,
        excluded: set[uuid.UUID],
        borrowed: set[uuid.UUID] | frozenset = frozenset(),
    ) -> bool:
        """Visible iff the owner org isn't excluded, or the plate is on
        active loan to the caller's org (``borrowed`` — read surfaces only)."""
        return self.can_view_owner(plate.owner_org_id, excluded) or plate.id in borrowed

    def can_view_owner(
        self, owner_org_id: uuid.UUID | None, excluded: set[uuid.UUID]
    ) -> bool:
        """Visibility by owner org alone — for org-owned things that aren't
        plates (plate groups). Same rule: hidden iff owner org is excluded.
        No loan carve-out — groups stay strict by design (S3/S4 scope)."""
        return owner_org_id not in excluded
