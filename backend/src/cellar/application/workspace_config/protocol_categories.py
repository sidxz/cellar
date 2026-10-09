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
from cellar.application.screening.protocol_naming_service import ProtocolNameService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.workspace_config.naming_changes import (
    apply_naming_change,
    compute_naming_change,
    plan_category,
    refuse_collisions,
)
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError
from cellar.domain.shared.protocol_naming import DEFAULT_CATEGORY_PATTERNS
from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.domain.workspace_config.repository import (
    ProtocolCategoryRepository,
    ProtocolFormRepository,
)


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
    """Renaming a category or editing its pattern relabels its protocols, so the edit is
    refused when two protocols would end up with the same name."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolCategoryRepository,
        dispatcher: EventDispatcherProtocol,
        *,
        protocol_repo: ProtocolRepository,
        names: ProtocolNameService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._protocols = protocol_repo
        self._names = names

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
            old_label, old_pattern = category.label, category.name_pattern
            category.update(label=input.label, name_pattern=input.name_pattern)
            plan = await plan_category(
                workspace_id=input.workspace_id,
                protocol_repo=self._protocols,
                names=self._names,
                label=old_label,
                pattern=category.name_pattern,
            )
            preview = await compute_naming_change(
                workspace_id=input.workspace_id,
                protocol_repo=self._protocols,
                names=self._names,
                plan=plan,
            )
            refused = refuse_collisions(preview)
            if isinstance(refused, Failure):
                return refused
            relabeled = []
            if category.label != old_label:
                for protocol in plan.protocols:
                    protocol.relabel_category(category.label)
                relabeled = plan.protocols
            await apply_naming_change(
                protocol_repo=self._protocols,
                names=self._names,
                plan=plan,
                preview=preview,
                reason="Category pattern changed"
                if category.name_pattern != old_pattern
                else "Category renamed",
                user_id=auth.user_id if auth else None,
                also_save=relabeled,
            )
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
        *,
        form_repo: ProtocolFormRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._protocol_repo = protocol_repo
        self._form_repo = form_repo

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
            # Its forms turn generic (FK SET NULL); none may collide with the generic default.
            await self._form_repo.clear_category_defaults(input.workspace_id, category.id)
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
