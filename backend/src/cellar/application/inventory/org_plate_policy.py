"""OrgPlatePolicy use cases — get-or-default read, full-field upsert write."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import (
    AuthContext,
    require_admin,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.enums import LoanConfirmationMode
from cellar.domain.inventory.org_plate_policy import OrgPlatePolicy
from cellar.domain.inventory.repository import OrgPlatePolicyRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class GetOrgPlatePolicyQuery(Query):
    workspace_id: uuid.UUID
    org_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class SetOrgPlatePolicyCommand(Command):
    workspace_id: uuid.UUID
    org_id: uuid.UUID
    require_approval: bool
    confirmation: str
    default_due_days: int | None


class GetOrgPlatePolicy:
    """Get-or-default read — never persists a row just for a GET."""

    def __init__(self, uow: UnitOfWork, repo: OrgPlatePolicyRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetOrgPlatePolicyQuery, auth: AuthContext | None = None
    ) -> Result[OrgPlatePolicy, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            policy = await self._repo.find_by_org(input.workspace_id, input.org_id)
            if policy is None:
                # Return in-memory defaults — no hidden write.
                # Policy is persisted on first explicit PUT.
                policy = OrgPlatePolicy.create_default(
                    workspace_id=input.workspace_id, org_id=input.org_id
                )
            return Success(policy)


class SetOrgPlatePolicy:
    """Full-field upsert — loads existing policy (or defaults), applies all fields, saves."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: OrgPlatePolicyRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: SetOrgPlatePolicyCommand, auth: AuthContext | None = None
    ) -> Result[OrgPlatePolicy, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            policy = await self._repo.find_by_org(input.workspace_id, input.org_id)
            if policy is None:
                policy = OrgPlatePolicy.create_default(
                    workspace_id=input.workspace_id, org_id=input.org_id
                )

            policy.update(
                require_approval=input.require_approval,
                confirmation=LoanConfirmationMode(input.confirmation),
                default_due_days=input.default_due_days,
            )

            await self._repo.save(policy)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(policy)
