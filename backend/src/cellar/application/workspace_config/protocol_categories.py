"""Protocol categories: each carries the name pattern its protocols follow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

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
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError
from cellar.domain.shared.protocol_naming import DEFAULT_CATEGORY_PATTERNS
from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.domain.workspace_config.repository import ProtocolCategoryRepository


@dataclass(frozen=True, kw_only=True)
class ListProtocolCategoriesQuery(Query):
    workspace_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CreateProtocolCategoryCommand(Command):
    workspace_id: uuid.UUID
    label: str
    name_pattern: str | None = None


@dataclass(frozen=True, kw_only=True)
class UpdateProtocolCategoryCommand(Command):
    workspace_id: uuid.UUID
    category_id: uuid.UUID
    label: str | None = None
    name_pattern: str | None = None


@dataclass(frozen=True, kw_only=True)
class DeleteProtocolCategoryCommand(Command):
    workspace_id: uuid.UUID
    category_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class SeedDefaultProtocolCategoriesCommand(Command):
    workspace_id: uuid.UUID


class ListProtocolCategories:
    def __init__(self, uow: UnitOfWork, repo: ProtocolCategoryRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListProtocolCategoriesQuery, auth: AuthContext | None = None
    ) -> Result[list[ProtocolCategory], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            return Success(await self._repo.find_by_workspace(input.workspace_id))


class CreateProtocolCategory:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolCategoryRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateProtocolCategoryCommand, auth: AuthContext | None = None
    ) -> Result[ProtocolCategory, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            if await self._repo.find_by_label(input.workspace_id, input.label):
                return Failure(ConflictError(f"Category '{input.label.strip()}' already exists"))
            category = ProtocolCategory.create(
                workspace_id=input.workspace_id, label=input.label, name_pattern=input.name_pattern
            )
            await self._repo.save(category)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(category)


class UpdateProtocolCategory:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolCategoryRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdateProtocolCategoryCommand, auth: AuthContext | None = None
    ) -> Result[ProtocolCategory, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            category = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.category_id
            )
            if category is None:
                return Failure(NotFoundError("ProtocolCategory", str(input.category_id)))
            if input.label is not None:
                other = await self._repo.find_by_label(input.workspace_id, input.label)
                if other is not None and other.id != category.id:
                    return Failure(
                        ConflictError(f"Category '{input.label.strip()}' already exists")
                    )
            category.update(label=input.label, name_pattern=input.name_pattern)
            await self._repo.save(category)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(category)


class DeleteProtocolCategory:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolCategoryRepository,
        protocol_repo: ProtocolRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._protocol_repo = protocol_repo

    async def __call__(
        self, input: DeleteProtocolCategoryCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            category = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.category_id
            )
            if category is None:
                return Failure(NotFoundError("ProtocolCategory", str(input.category_id)))
            in_use = await self._protocol_repo.count_by_category(
                input.workspace_id, category.label
            )
            if in_use:
                return Failure(
                    ConflictError(
                        f"{in_use} protocol(s) use '{category.label}'; "
                        "move them to another category first"
                    )
                )
            await self._repo.delete(input.workspace_id, category.id)
            await self._uow.commit()
        return Success(None)


class SeedDefaultProtocolCategories:
    """Adds any shipped default category the workspace lacks. Never edits existing ones."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolCategoryRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: SeedDefaultProtocolCategoriesCommand, auth: AuthContext | None = None
    ) -> Result[list[ProtocolCategory], DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            for label in DEFAULT_CATEGORY_PATTERNS:
                if await self._repo.find_by_label(input.workspace_id, label) is None:
                    await self._repo.save(
                        ProtocolCategory.create(workspace_id=input.workspace_id, label=label)
                    )
            categories = await self._repo.find_by_workspace(input.workspace_id)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(categories)
