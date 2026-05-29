"""CollectionImportTemplate use cases — CRUD + header-match scoring."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)
from cellar.domain.research_organization.repository import (
    CollectionImportTemplateRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError

# ---------------------------------------------------------------------------
# Commands / Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreateCollectionImportTemplateCommand(Command):
    workspace_id: uuid.UUID
    name: str
    column_mapping: dict[str, str]
    description: str | None = None
    created_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class UpdateCollectionImportTemplateCommand(Command):
    workspace_id: uuid.UUID
    template_id: uuid.UUID
    name: str | None = None
    description: str | None = None
    column_mapping: dict[str, str] | None = None


@dataclass(frozen=True, kw_only=True)
class DeleteCollectionImportTemplateCommand(Command):
    workspace_id: uuid.UUID
    template_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListCollectionImportTemplatesQuery(Query):
    workspace_id: uuid.UUID


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------


class CreateCollectionImportTemplate:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: CollectionImportTemplateRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: CreateCollectionImportTemplateCommand,
        auth: AuthContext | None = None,
    ) -> Result[CollectionImportTemplate, DomainError]:
        try:
            require_editor(auth)
            require_same_workspace(auth, input.workspace_id)
        except DomainError as exc:
            return Failure(exc)

        async with self._uow:
            template = CollectionImportTemplate.create(
                workspace_id=input.workspace_id,
                name=input.name,
                column_mapping=input.column_mapping,
                description=input.description,
                created_by=input.created_by,
            )
            await self._repo.save(template)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(template)


class UpdateCollectionImportTemplate:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: CollectionImportTemplateRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: UpdateCollectionImportTemplateCommand,
        auth: AuthContext | None = None,
    ) -> Result[CollectionImportTemplate, DomainError]:
        try:
            require_editor(auth)
            require_same_workspace(auth, input.workspace_id)
        except DomainError as exc:
            return Failure(exc)

        async with self._uow:
            template = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.template_id
            )
            if template is None:
                return Failure(
                    NotFoundError("CollectionImportTemplate", str(input.template_id))
                )
            template.update(
                name=input.name,
                description=input.description,
                column_mapping=input.column_mapping,
            )
            await self._repo.save(template)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(template)


class DeleteCollectionImportTemplate:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: CollectionImportTemplateRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: DeleteCollectionImportTemplateCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        try:
            require_editor(auth)
            require_same_workspace(auth, input.workspace_id)
        except DomainError as exc:
            return Failure(exc)

        async with self._uow:
            template = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.template_id
            )
            if template is None:
                return Failure(
                    NotFoundError("CollectionImportTemplate", str(input.template_id))
                )
            await self._repo.delete(input.workspace_id, input.template_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class ListCollectionImportTemplates:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: CollectionImportTemplateRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListCollectionImportTemplatesQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[CollectionImportTemplate], DomainError]:
        try:
            require_same_workspace(auth, input.workspace_id)
        except DomainError as exc:
            return Failure(exc)

        async with self._uow:
            templates = await self._repo.find_by_workspace(input.workspace_id)
            return Success(templates)


# ---------------------------------------------------------------------------
# Header-match scoring (for auto-suggestion in the wizard)
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def score_template_against_headers(
    template: CollectionImportTemplate, headers: list[str]
) -> float:
    """Return a 0-1 score for how well a template's mapping matches headers.

    A template scores 1.0 when every header it references is present in the
    file; partial matches are weighted by the fraction of references found.
    """
    norm_headers = {_norm(h) for h in headers}
    refs = [v for v in template.column_mapping.values() if v]
    if not refs:
        return 0.0
    matched = sum(1 for r in refs if _norm(r) in norm_headers)
    return matched / len(refs)
