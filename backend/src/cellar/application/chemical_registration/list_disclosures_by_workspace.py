"""ListDisclosuresByWorkspace query — all disclosures in workspace, optional status filter."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.disclosure_request import DisclosureRequest
from cellar.domain.chemical_registration.repository import DisclosureRequestRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListDisclosuresByWorkspaceQuery(Query):
    workspace_id: uuid.UUID
    status: str | None = None
    cursor_id: uuid.UUID | None = None
    limit: int | None = None


class ListDisclosuresByWorkspace:
    def __init__(
        self,
        uow: UnitOfWork,
        disclosure_repo: DisclosureRequestRepository,
    ) -> None:
        self._uow = uow
        self._disclosure_repo = disclosure_repo

    async def __call__(
        self, input: ListDisclosuresByWorkspaceQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[DisclosureRequest], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None

            disclosures = await self._disclosure_repo.find_by_workspace(
                input.workspace_id,
                status=input.status,
                cursor_id=input.cursor_id,
                limit=fetch_limit,
            )

            next_cursor: str | None = None
            if effective_limit is not None and len(disclosures) > effective_limit:
                disclosures = disclosures[:effective_limit]
                next_cursor = str(disclosures[-1].id)

            return Success(PageResult(items=disclosures, next_cursor=next_cursor))
