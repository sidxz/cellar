"""ListBulkRegistrationItems — paged read of per-row outcomes.

Drives the per-row results table on the wizard's Summary step so users can
see which compounds were registered, deduped, deferred, or failed (with
error messages).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.chemical_registration.bulk_registration_item_reader import (
    BulkRegistrationItemPage,
    BulkRegistrationItemReader,
)
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.enums import BulkRegistrationItemAction
from cellar.domain.chemical_registration.repository import (
    BulkRegistrationRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class ListBulkRegistrationItemsQuery(Query):
    workspace_id: uuid.UUID
    # Either bulk_registration_id (DB id) OR workflow_id (Temporal id) may be
    # supplied. The wizard only knows the workflow_id, but admin views may
    # pass the aggregate id directly.
    bulk_registration_id: uuid.UUID | None = None
    workflow_id: str | None = None
    action: str | None = None
    limit: int = 50
    offset: int = 0


class ListBulkRegistrationItems:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        repo: BulkRegistrationRepository,
        reader: BulkRegistrationItemReader,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._reader = reader

    async def __call__(
        self,
        input: ListBulkRegistrationItemsQuery,
        auth: AuthContext | None = None,
    ) -> Result[BulkRegistrationItemPage, DomainError]:
        require_same_workspace(auth, input.workspace_id)

        if input.bulk_registration_id is None and not input.workflow_id:
            return Failure(
                ValidationError("Either bulk_registration_id or workflow_id is required")
            )
        if input.action is not None:
            try:
                BulkRegistrationItemAction(input.action)
            except ValueError:
                return Failure(ValidationError(f"Unknown action: {input.action!r}"))
        if input.limit <= 0 or input.limit > 500:
            return Failure(ValidationError("limit must be in [1, 500]"))
        if input.offset < 0:
            return Failure(ValidationError("offset must be non-negative"))

        async with self._uow:
            bulk_reg_id = input.bulk_registration_id
            if bulk_reg_id is None:
                assert input.workflow_id is not None
                bulk_reg = await self._repo.find_by_workflow_id_in_workspace(
                    input.workspace_id, input.workflow_id
                )
                if bulk_reg is None:
                    return Failure(NotFoundError("BulkRegistration", input.workflow_id))
                bulk_reg_id = bulk_reg.id
            else:
                bulk_reg = await self._repo.find_by_id_in_workspace(
                    input.workspace_id, bulk_reg_id
                )
                if bulk_reg is None:
                    return Failure(NotFoundError("BulkRegistration", str(bulk_reg_id)))

        # Reader uses its own session_factory — runs outside the UoW txn.
        page = await self._reader.list_items(
            workspace_id=input.workspace_id,
            bulk_registration_id=bulk_reg_id,
            action=input.action,
            limit=input.limit,
            offset=input.offset,
        )
        return Success(page)
