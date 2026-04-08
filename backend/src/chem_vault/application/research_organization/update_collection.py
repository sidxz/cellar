"""UpdateCollection command — partial update of an existing collection."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.domain.research_organization.collection import Collection, CollectionVisibility
from chem_vault.domain.research_organization.repository import CollectionRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class UpdateCollectionCommand(Command):
    workspace_id: uuid.UUID
    collection_id: uuid.UUID
    name: str | None = None
    description: str | None | object = UNSET
    project_id: uuid.UUID | None | object = UNSET
    owned_by_org_id: uuid.UUID | None | object = UNSET
    visibility: str | None = None


class UpdateCollection:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: CollectionRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdateCollectionCommand, auth: AuthContext | None = None
    ) -> Result[Collection, DomainError]:
        require_editor(auth)

        async with self._uow:
            collection = await self._repo.find_by_id_in_workspace(input.workspace_id, input.collection_id)
            if collection is None:
                return Failure(NotFoundError("Collection", str(input.collection_id)))

            # Build kwargs — only include fields that were provided
            fields: dict[str, Any] = {}
            if input.name is not None:
                fields["name"] = input.name
            if input.description is not UNSET:
                fields["description"] = input.description
            if input.project_id is not UNSET:
                fields["project_id"] = input.project_id
            if input.owned_by_org_id is not UNSET:
                fields["owned_by_org_id"] = input.owned_by_org_id
            if input.visibility is not None:
                fields["visibility"] = CollectionVisibility(input.visibility)

            if fields:
                collection.update(**fields)
            await self._repo.save(collection)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(collection)
