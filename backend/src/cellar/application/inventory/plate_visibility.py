"""PlateVisibilityService — strict org scoping for plates and org-owned things
(spec 2026-08-25 §3), plus the borrowed-plate read carve-out (loan clause)."""

from __future__ import annotations

import uuid

from cellar.application.auth import AuthContext
from cellar.application.shared.org_directory import OrgDirectoryPort
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.repository import PlateLoanRepository


class PlateVisibilityService:
    """Strict rule: a caller sees plates of their own org (plus plates on
    active loan to it — read surfaces only); workspace admins and system
    calls (``auth is None``) see everything.

    ``excluded_org_ids`` returns "every org in the directory except mine" so
    the existing call sites keep their exclusion-set plumbing unchanged.
    # ponytail: an inclusion scope (visible_owner_org_id | None) would drop
    # the directory dependency; only worth the ~20-site refactor if the
    # directory ever proves unreliable.

    Write-path narrowing is deliberate: Update/MapWells/ChangeStatus/Derive/
    Delete, export, tag verbs, and plate groups never fetch a borrowed set
    and call ``can_view``/``can_view_owner`` with their default (empty), so a
    borrower can SEE a loaned plate but not modify it. Only the read surfaces
    — GetPlate, ListPlates, ListChildren, molecule->plates read model — pass
    a real one.
    """

    def __init__(
        self,
        org_directory: OrgDirectoryPort | None = None,
        loan_repo: PlateLoanRepository | None = None,
    ) -> None:
        self._org_directory = org_directory
        self._loan_repo = loan_repo

    async def excluded_org_ids(
        self, workspace_id: uuid.UUID, auth: AuthContext | None
    ) -> set[uuid.UUID]:
        """Every directory org id except the caller's own. Empty for system
        calls and workspace admins. Fails closed (raises) when a non-admin
        caller arrives and no directory is wired."""
        if auth is None or auth.is_admin:
            return set()
        if self._org_directory is None:
            raise RuntimeError(
                "PlateVisibilityService needs an org directory for non-admin callers"
            )
        all_ids = {o.id for o in await self._org_directory.list_orgs()}
        return all_ids - {auth.org_id}

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
