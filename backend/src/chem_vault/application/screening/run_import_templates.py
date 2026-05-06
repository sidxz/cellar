"""RunImportTemplate use cases — CRUD + header-match scoring."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
)
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.repository import RunImportTemplateRepository
from chem_vault.domain.screening_assay.run_import_template import RunImportTemplate
from chem_vault.domain.shared.errors import DomainError, NotFoundError


# ---------------------------------------------------------------------------
# Commands / Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreateRunImportTemplateCommand(Command):
    workspace_id: uuid.UUID
    name: str
    column_mapping: dict[str, Any]
    description: str | None = None
    created_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class UpdateRunImportTemplateCommand(Command):
    workspace_id: uuid.UUID
    template_id: uuid.UUID
    name: str | None = None
    description: str | None = None
    column_mapping: dict[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class DeleteRunImportTemplateCommand(Command):
    workspace_id: uuid.UUID
    template_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListRunImportTemplatesQuery(Query):
    workspace_id: uuid.UUID


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------


class CreateRunImportTemplate:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunImportTemplateRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: CreateRunImportTemplateCommand,
        auth: AuthContext | None = None,
    ) -> Result[RunImportTemplate, DomainError]:
        try:
            require_editor(auth)
            require_same_workspace(auth, input.workspace_id)
        except DomainError as exc:
            return Failure(exc)

        async with self._uow:
            template = RunImportTemplate.create(
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


class UpdateRunImportTemplate:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunImportTemplateRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: UpdateRunImportTemplateCommand,
        auth: AuthContext | None = None,
    ) -> Result[RunImportTemplate, DomainError]:
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
                    NotFoundError("RunImportTemplate", str(input.template_id))
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


class DeleteRunImportTemplate:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunImportTemplateRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: DeleteRunImportTemplateCommand,
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
                    NotFoundError("RunImportTemplate", str(input.template_id))
                )
            await self._repo.delete(input.workspace_id, input.template_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class ListRunImportTemplates:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunImportTemplateRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListRunImportTemplatesQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[RunImportTemplate], DomainError]:
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
    template: RunImportTemplate, headers: list[str]
) -> float:
    """Return a 0–1 score for how well a template's mapping matches headers.

    A template scores 1.0 when every header it references is present in the
    file; partial matches are weighted by the fraction of references found.
    The well column is required — score is 0 if absent.
    """
    norm_headers = {_norm(h) for h in headers}
    refs = _collect_template_refs(template.column_mapping)
    if not refs:
        return 0.0
    well_ref = template.column_mapping.get("well")
    if well_ref and _norm(well_ref) not in norm_headers:
        return 0.0
    matched = sum(1 for r in refs if _norm(r) in norm_headers)
    return matched / len(refs)


def _collect_template_refs(mapping: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key, value in mapping.items():
        if value is None:
            continue
        if key == "readout_headers" and isinstance(value, list):
            refs.extend(str(v) for v in value if v)
        elif isinstance(value, str) and value:
            refs.append(value)
    return refs
