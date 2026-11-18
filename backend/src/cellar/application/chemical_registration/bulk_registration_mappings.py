"""Saved bulk-registration column mappings — list, create, update, delete."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_same_workspace,
)
from cellar.application.chemical_registration.bulk_column_mapping import ColumnMapping
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.bulk_registration_mapping import (
    BulkRegistrationMapping,
)
from cellar.domain.chemical_registration.repository import BulkRegistrationMappingRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError


def _valid_columns(columns: list[dict]) -> Result[list[dict], DomainError]:
    """Same rules as a mapping sent with an upload, minus the file's headers."""
    try:
        mapping = ColumnMapping.from_dict({"columns": columns})
    except ValidationError as err:
        return Failure(err)
    headers = [c.header for c in mapping.columns]
    if len(set(headers)) != len(headers):
        return Failure(ValidationError("Each column can appear only once in a mapping"))
    err = mapping.validate(headers, structure_implied=True)
    if err is not None:
        return Failure(err)
    return Success(mapping.to_dict()["columns"])


async def _name_taken(
    repo: BulkRegistrationMappingRepository,
    workspace_id: uuid.UUID,
    name: str,
    except_id: uuid.UUID | None = None,
) -> bool:
    wanted = name.strip().lower()
    return any(
        m.name.lower() == wanted and m.id != except_id
        for m in await repo.find_by_workspace(workspace_id)
    )


@dataclass(frozen=True, kw_only=True)
class ListBulkRegistrationMappingsQuery(Query):
    workspace_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CreateBulkRegistrationMappingCommand(Command):
    workspace_id: uuid.UUID
    name: str
    columns: list[dict]
    created_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class UpdateBulkRegistrationMappingCommand(Command):
    workspace_id: uuid.UUID
    mapping_id: uuid.UUID
    name: str | None = None
    columns: list[dict] | None = None


@dataclass(frozen=True, kw_only=True)
class DeleteBulkRegistrationMappingCommand(Command):
    workspace_id: uuid.UUID
    mapping_id: uuid.UUID


class ListBulkRegistrationMappings:
    def __init__(self, uow: UnitOfWork, repo: BulkRegistrationMappingRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListBulkRegistrationMappingsQuery, auth: AuthContext | None = None
    ) -> Result[list[BulkRegistrationMapping], DomainError]:
        require_authenticated(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            return Success(await self._repo.find_by_workspace(input.workspace_id))


class _MappingWrite:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: BulkRegistrationMappingRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher


class CreateBulkRegistrationMapping(_MappingWrite):
    async def __call__(
        self, input: CreateBulkRegistrationMappingCommand, auth: AuthContext | None = None
    ) -> Result[BulkRegistrationMapping, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        columns = _valid_columns(input.columns)
        if isinstance(columns, Failure):
            return columns
        async with self._uow:
            if await _name_taken(self._repo, input.workspace_id, input.name):
                return Failure(ConflictError(f"A saved mapping named '{input.name}' exists"))
            try:
                mapping = BulkRegistrationMapping.create(
                    workspace_id=input.workspace_id,
                    name=input.name,
                    columns=columns.unwrap(),
                    created_by=input.created_by,
                )
            except ValidationError as err:
                return Failure(err)
            await self._repo.save(mapping)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(mapping)


class UpdateBulkRegistrationMapping(_MappingWrite):
    async def __call__(
        self, input: UpdateBulkRegistrationMappingCommand, auth: AuthContext | None = None
    ) -> Result[BulkRegistrationMapping, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        columns: list[dict] | None = None
        if input.columns is not None:
            checked = _valid_columns(input.columns)
            if isinstance(checked, Failure):
                return checked
            columns = checked.unwrap()
        async with self._uow:
            mapping = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.mapping_id
            )
            if mapping is None:
                return Failure(NotFoundError("BulkRegistrationMapping", str(input.mapping_id)))
            if input.name is not None and await _name_taken(
                self._repo, input.workspace_id, input.name, except_id=mapping.id
            ):
                return Failure(ConflictError(f"A saved mapping named '{input.name}' exists"))
            try:
                mapping.update(name=input.name, columns=columns)
            except ValidationError as err:
                return Failure(err)
            await self._repo.save(mapping)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(mapping)


class DeleteBulkRegistrationMapping(_MappingWrite):
    async def __call__(
        self, input: DeleteBulkRegistrationMappingCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            mapping = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.mapping_id
            )
            if mapping is None:
                return Failure(NotFoundError("BulkRegistrationMapping", str(input.mapping_id)))
            await self._repo.delete(input.workspace_id, input.mapping_id)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(None)
