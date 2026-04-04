"""Molecule identifier CRUD -- add, remove, list identifiers on a molecule."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.enums import IdentifierType
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError


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
            mol = await self._repo.find_by_id(input.molecule_id)
            if mol is None or mol.workspace_id != input.workspace_id:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            try:
                identifier = MoleculeIdentifier.create(
                    molecule_id=mol.id,
                    identifier=input.identifier,
                    identifier_type=IdentifierType(input.identifier_type),
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
            mol = await self._repo.find_by_id(input.molecule_id)
            if mol is None or mol.workspace_id != input.workspace_id:
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
        self, input: ListIdentifiersQuery
    ) -> Result[list[MoleculeIdentifier], DomainError]:
        async with self._uow:
            mol = await self._repo.find_by_id(input.molecule_id)
            if mol is None or mol.workspace_id != input.workspace_id:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))
            return Success(mol.identifiers)
