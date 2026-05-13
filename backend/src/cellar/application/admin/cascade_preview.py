# application/admin/cascade_preview.py
from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.admin.admin_delete_registry import get_entry
from cellar.application.admin.cascade_service import CascadeService
from cellar.application.admin.tier2_entities import TIER2_ENTITY_TYPES
from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.cascade import CascadeNode
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
)


@dataclass(frozen=True, kw_only=True)
class CascadePreviewQuery(Command):
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID


class CascadePreview:
    def __init__(self, uow: UnitOfWork, cascade_service: CascadeService) -> None:
        self._uow = uow
        self._cascade_service = cascade_service

    async def __call__(
        self,
        input: CascadePreviewQuery,
        auth: AuthContext | None = None,
    ) -> Result[CascadeNode, DomainError]:
        require_admin(auth)
        if input.entity_type not in TIER2_ENTITY_TYPES:
            return Failure(NotFoundError("entity_type", input.entity_type))
        entry = get_entry(input.entity_type)
        if entry is None:
            return Failure(NotFoundError("entity_type", input.entity_type))

        async with self._uow:
            node = await self._cascade_service.preview(
                parent_table=entry.table,
                parent_id=input.entity_id,
                workspace_id=input.workspace_id,
            )
            return Success(node)
