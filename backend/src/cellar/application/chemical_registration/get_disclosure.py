"""GetDisclosure query — returns a single disclosure request by ID."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.disclosure_request import DisclosureRequest
from cellar.domain.chemical_registration.repository import DisclosureRequestRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetDisclosureQuery(Query):
    """Input for fetching a single disclosure request."""

    workspace_id: uuid.UUID
    disclosure_id: uuid.UUID


class GetDisclosure:
    """Query use case: fetch a disclosure request by its ID.

    Workspace isolation enforced by ``find_by_id_in_workspace``.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        disclosure_repo: DisclosureRequestRepository,
    ) -> None:
        self._uow = uow
        self._disclosure_repo = disclosure_repo

    async def __call__(
        self, input: GetDisclosureQuery, auth: AuthContext | None = None
    ) -> Result[DisclosureRequest, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            dr = await self._disclosure_repo.find_by_id_in_workspace(
                input.workspace_id, input.disclosure_id
            )
            if dr is None:
                return Failure(NotFoundError("DisclosureRequest", str(input.disclosure_id)))
            return Success(dr)
