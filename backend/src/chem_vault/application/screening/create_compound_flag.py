"""CreateCompoundFlag use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.compound_flag import CompoundFlag, FlagType
from chem_vault.domain.screening_assay.repository import CompoundFlagRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class CreateCompoundFlagCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    protocol_id: uuid.UUID
    flag_type: str = "star"
    note: str | None = None


class CreateCompoundFlag:
    def __init__(self, uow: UnitOfWork, repo: CompoundFlagRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: CreateCompoundFlagCommand, auth: AuthContext | None = None
    ) -> Result[CompoundFlag, DomainError]:
        require_editor(auth)

        flag = CompoundFlag(
            workspace_id=input.workspace_id,
            molecule_id=input.molecule_id,
            protocol_id=input.protocol_id,
            flagged_by=auth.user_id,  # type: ignore[union-attr]
            flag_type=FlagType(input.flag_type),
            note=input.note,
            created_at=datetime.now(UTC),
        )

        async with self._uow:
            await self._repo.save(flag)
            await self._uow.commit()

        return Success(flag)
