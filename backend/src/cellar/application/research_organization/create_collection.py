"""CreateCollection command — create a new molecule collection in a workspace.

Optionally seeds it with molecules in the same transaction: every id must
resolve in the workspace, or nothing is created.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.molecule_resolver import (
    MoleculeReference,
    MoleculeResolver,
    RefType,
)
from cellar.application.shared.org_directory import OrgDirectoryPort, unpickable_org
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.collection import Collection, CollectionVisibility
from cellar.domain.research_organization.enums import CollectionType
from cellar.domain.research_organization.events import CollectionMembersChanged
from cellar.domain.research_organization.repository import CollectionRepository
from cellar.domain.shared.errors import DomainError, ValidationError


@dataclass(frozen=True, kw_only=True)
class CreateCollectionCommand(Command):
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    project_id: uuid.UUID | None = None
    # A Duar org the creator picked; None = the creator's own org.
    owner_org_id: uuid.UUID | None = None
    created_by: uuid.UUID
    visibility: str = "private"
    type: str = "generic"
    molecule_ids: tuple[uuid.UUID, ...] = ()


class CreateCollection:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: CollectionRepository,
        dispatcher: EventDispatcherProtocol,
        resolver: MoleculeResolver,
        org_directory: OrgDirectoryPort | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._resolver = resolver
        self._org_directory = org_directory

    async def __call__(
        self, input: CreateCollectionCommand, auth: AuthContext | None = None
    ) -> Result[Collection, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        creator_org_id = auth.org_id if auth else None
        if (
            input.owner_org_id is not None
            and input.owner_org_id != creator_org_id
            and self._org_directory is not None
            and (err := await unpickable_org(self._org_directory, input.owner_org_id))
        ):
            return Failure(err)

        molecule_ids = list(dict.fromkeys(input.molecule_ids))
        async with self._uow:
            if molecule_ids:
                refs = [MoleculeReference(str(m), RefType.UUID) for m in molecule_ids]
                _, unresolved = await self._resolver.resolve(input.workspace_id, refs)
                if unresolved:
                    return Failure(
                        ValidationError(
                            f"{len(unresolved)} molecule(s) not found in this workspace",
                            detail=", ".join(u.ref.value for u in unresolved),
                        )
                    )

            collection = Collection.create(
                workspace_id=input.workspace_id,
                name=input.name,
                description=input.description,
                project_id=input.project_id,
                owner_org_id=input.owner_org_id,
                created_by=input.created_by,
                created_by_org_id=creator_org_id,
                visibility=CollectionVisibility(input.visibility),
                type=CollectionType(input.type),
            )
            await self._repo.save(collection)
            if molecule_ids:
                await self._repo.add_molecules(input.workspace_id, collection.id, molecule_ids)
                collection.molecule_count = len(molecule_ids)
                collection.register_event(
                    CollectionMembersChanged(
                        aggregate_id=collection.id,
                        aggregate_type="Collection",
                        workspace_id=collection.workspace_id,
                        added_ids=molecule_ids,
                        removed_ids=[],
                    )
                )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(collection)
