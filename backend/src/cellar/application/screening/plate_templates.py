"""PlateTemplate use cases — CRUD for reusable plate layout templates."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_workspace_role
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import PlateFormat
from cellar.domain.screening_assay.plate_template import PlateTemplate
from cellar.domain.screening_assay.repository import PlateTemplateRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreatePlateTemplateCommand(Command):
    workspace_id: uuid.UUID
    name: str
    format: PlateFormat
    template_map: dict[str, Any]
    description: str | None = None
    created_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class UpdatePlateTemplateCommand(Command):
    workspace_id: uuid.UUID
    template_id: uuid.UUID
    name: str | None = None
    format: PlateFormat | None = None
    template_map: dict[str, Any] | None = None
    description: str | None = UNSET


@dataclass(frozen=True, kw_only=True)
class DeletePlateTemplateCommand(Command):
    workspace_id: uuid.UUID
    template_id: uuid.UUID


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class GetPlateTemplateQuery(Query):
    workspace_id: uuid.UUID
    template_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListPlateTemplatesQuery(Query):
    workspace_id: uuid.UUID


# ---------------------------------------------------------------------------
# Use Cases
# ---------------------------------------------------------------------------


class CreatePlateTemplate:
    def __init__(
        self, uow: UnitOfWork, repo: PlateTemplateRepository, dispatcher: EventDispatcherProtocol
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreatePlateTemplateCommand, auth: AuthContext | None = None
    ) -> Result[PlateTemplate, DomainError]:
        require_editor(auth)

        async with self._uow:
            template = PlateTemplate.create(
                workspace_id=input.workspace_id,
                name=input.name,
                format=input.format,
                template_map=input.template_map,
                description=input.description,
                created_by=input.created_by,
            )
            await self._repo.save(template)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(template)


class UpdatePlateTemplate:
    def __init__(
        self, uow: UnitOfWork, repo: PlateTemplateRepository, dispatcher: EventDispatcherProtocol
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdatePlateTemplateCommand, auth: AuthContext | None = None
    ) -> Result[PlateTemplate, DomainError]:
        require_editor(auth)

        async with self._uow:
            template = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.template_id
            )
            if template is None:
                return Failure(NotFoundError("PlateTemplate", str(input.template_id)))

            # Build kwargs — only include description when explicitly provided
            kwargs: dict[str, Any] = {}
            if input.name is not None:
                kwargs["name"] = input.name
            if input.format is not None:
                kwargs["format"] = input.format
            if input.template_map is not None:
                kwargs["template_map"] = input.template_map
            if input.description is not UNSET:
                kwargs["description"] = input.description

            if kwargs:
                template.update(**kwargs)
                await self._repo.save(template)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(template)


class DeletePlateTemplate:
    def __init__(
        self, uow: UnitOfWork, repo: PlateTemplateRepository, dispatcher: EventDispatcherProtocol
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeletePlateTemplateCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            template = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.template_id
            )
            if template is None:
                return Failure(NotFoundError("PlateTemplate", str(input.template_id)))

            ref_count = await self._repo.count_references(input.workspace_id, input.template_id)
            if ref_count > 0:
                return Failure(
                    ConflictError(
                        f"PlateTemplate is referenced by {ref_count} plate(s)/run(s) and cannot be deleted"
                    )
                )

            await self._repo.delete(input.workspace_id, input.template_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class GetPlateTemplate:
    def __init__(self, uow: UnitOfWork, repo: PlateTemplateRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetPlateTemplateQuery, auth: AuthContext | None = None
    ) -> Result[PlateTemplate, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            template = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.template_id
            )
            if template is None:
                return Failure(NotFoundError("PlateTemplate", str(input.template_id)))
            return Success(template)


class ListPlateTemplates:
    def __init__(self, uow: UnitOfWork, repo: PlateTemplateRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListPlateTemplatesQuery, auth: AuthContext | None = None
    ) -> Result[list[PlateTemplate], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            templates = await self._repo.find_by_workspace(input.workspace_id)
            return Success(templates)
