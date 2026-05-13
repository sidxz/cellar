"""UpdateSaltEntry command — update name, smiles, molecular_weight, or active status."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.workspace_config.repository import SaltEntryRepository
from cellar.domain.workspace_config.salt_entry import SaltEntry


@dataclass(frozen=True, kw_only=True)
class UpdateSaltEntryCommand(Command):
    workspace_id: uuid.UUID
    entry_id: uuid.UUID
    name: str | object = UNSET
    smiles: str | object = UNSET
    molecular_weight: float | object = UNSET
    is_active: bool | object = UNSET


class UpdateSaltEntry:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SaltEntryRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdateSaltEntryCommand, auth: AuthContext | None = None
    ) -> Result[SaltEntry, DomainError]:
        require_editor(auth)

        async with self._uow:
            entry = await self._repo.find_by_id_in_workspace(input.workspace_id, input.entry_id)
            if entry is None:
                return Failure(NotFoundError("SaltEntry", str(input.entry_id)))

            # Build kwargs for update() from non-UNSET fields
            update_kwargs: dict[str, Any] = {}
            for attr in ("name", "smiles", "molecular_weight"):
                val = getattr(input, attr)
                if val is not UNSET:
                    update_kwargs[attr] = val

            if update_kwargs:
                entry.update(**update_kwargs)

            # Handle is_active separately (activate/deactivate calls)
            if input.is_active is not UNSET:
                if input.is_active:
                    entry.activate()
                else:
                    entry.deactivate()

            await self._repo.save(entry)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(entry)
