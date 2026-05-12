"""Molecule identifier CRUD -- add, remove, list identifiers on a molecule."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_workspace_role
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError


# ---------------------------------------------------------------------------
# Commands / Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AddIdentifierCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    identifier: str
    identifier_type: str
    source: str
    registered_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RemoveIdentifierCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    identifier_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListIdentifiersQuery(Query):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


# ---------------------------------------------------------------------------
# Use Cases
# ---------------------------------------------------------------------------


class AddIdentifier:
    """Add an external identifier to a molecule."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: AddIdentifierCommand,
        auth: AuthContext | None = None,
    ) -> Result[Molecule, DomainError]:
        require_editor(auth)

        async with self._uow:
            mol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            # Workspace-unique check: identifier must not exist on another molecule
            existing = await self._repo.find_by_identifier(input.workspace_id, input.identifier)
            if existing is not None and existing.id != mol.id:
                return Failure(
                    ConflictError(
                        f"Identifier '{input.identifier}' is already assigned to "
                        f"molecule '{existing.registration_number.value}'"
                    )
                )

            try:
                identifier = MoleculeIdentifier.create(
                    molecule_id=mol.id,
                    identifier=input.identifier,
                    identifier_type=input.identifier_type,
                    source=input.source,
                    registered_by=input.registered_by,
                )
                mol.add_identifier(identifier)
            except (ValidationError, ValueError) as exc:
                if isinstance(exc, ValueError):
                    return Failure(ValidationError(str(exc)))
                return Failure(exc)

            await self._repo.save(mol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(mol)


class RemoveIdentifier:
    """Remove an identifier from a molecule by ID."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: RemoveIdentifierCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            mol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            try:
                mol.remove_identifier(input.identifier_id)
            except ValidationError as exc:
                return Failure(exc)

            await self._repo.save(mol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class ListIdentifiers:
    """List all identifiers on a molecule (read-only)."""

    def __init__(self, uow: UnitOfWork, repo: MoleculeRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListIdentifiersQuery, auth: AuthContext | None = None
    ) -> Result[list[MoleculeIdentifier], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            mol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))
            return Success(mol.identifiers)
