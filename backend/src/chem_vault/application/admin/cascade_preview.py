# application/admin/cascade_preview.py
from __future__ import annotations
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.admin.admin_delete_registry import get_entry
from chem_vault.application.auth import AuthContext, require_admin
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.cascade import CascadeNode
from chem_vault.domain.shared.errors import (
    AuthorizationError, DomainError, NotFoundError,
)
from chem_vault.infrastructure.cascade.cascade_runner import CascadeRunner

# Tier-2 is gated to these entity types only.
TIER2_ENTITY_TYPES = frozenset({"protocol", "run", "molecule"})


@dataclass(frozen=True, kw_only=True)
class CascadePreviewQuery(Command):
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID


class CascadePreview:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self, input: CascadePreviewQuery, auth: AuthContext | None = None,
    ) -> Result[CascadeNode, DomainError]:
        try:
            require_admin(auth)
        except AuthorizationError as e:
            return Failure(e)
        if input.entity_type not in TIER2_ENTITY_TYPES:
            return Failure(NotFoundError("entity_type", input.entity_type))
        entry = get_entry(input.entity_type)
        if entry is None:
            return Failure(NotFoundError("entity_type", input.entity_type))

        async with self._uow:
            runner = CascadeRunner(self._uow.session)  # type: ignore[attr-defined]
            node = await runner.preview(
                parent_table=entry.table, parent_id=input.entity_id,
            )
            return Success(node)
