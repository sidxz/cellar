"""Correct who disclosed a compound and for which Duar org: an admin or its registrant."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_admin_or_user,
    require_authenticated,
    require_editor,
    require_same_workspace,
)
from cellar.application.chemical_registration.discloser_pick import check_discloser_pick
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.org_directory import OrgDirectoryPort
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ChangeDiscloserCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    # UNSET = keep as is (an org-only correction keeps the person, and vice versa).
    disclosed_by: uuid.UUID | object = UNSET
    disclosed_by_org_id: uuid.UUID | object | None = UNSET


class ChangeDiscloser:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
        org_directory: OrgDirectoryPort,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._org_directory = org_directory

    async def __call__(
        self, input: ChangeDiscloserCommand, auth: AuthContext | None = None
    ) -> Result[Molecule, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            mol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))
            require_admin_or_user(auth, mol.registered_by)
            fields: dict[str, Any] = {}
            if input.disclosed_by is not UNSET:
                fields["disclosed_by"] = input.disclosed_by
            if input.disclosed_by_org_id is not UNSET:
                fields["disclosed_by_org_id"] = input.disclosed_by_org_id
            # Only what changes is checked: a discloser who has since left keeps their
            # credit through an org correction.
            new_person = fields.get("disclosed_by")
            if err := await check_discloser_pick(
                auth,
                self._org_directory,
                disclosed_by=new_person if new_person != mol.disclosed_by else None,
                disclosed_by_org_id=fields.get("disclosed_by_org_id"),
            ):
                return Failure(err)
            try:
                mol.change_discloser(**fields)
            except DomainError as e:
                return Failure(e)
            await self._repo.save(mol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(mol)
