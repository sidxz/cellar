"""BulkAddBatchIdentifiers — preview or commit a batch of external alias additions.

The chemist uploads a CSV of (cellar_batch_ref, external_identifier) pairs.
For each row, we resolve the Cellar batch (canonical batch_number OR
molecule_reg + sequence), check the alias uniqueness, and report one of:
resolved / not_found / conflict / already_mapped / error.

dry_run=True returns outcomes without saving. dry_run=False saves only the
resolved rows (skips the others, no transaction rollback for conflict rows
— they're reported back to the chemist for separate handling).
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from returns.result import Result, Success

from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings

RowStatus = Literal["resolved", "not_found", "conflict", "already_mapped", "error"]


@dataclass(frozen=True, kw_only=True)
class BulkIdentifierRow:
    row_index: int
    cellar_batch_number: str | None
    cellar_molecule_reg_number: str | None
    cellar_batch_sequence: int | None
    external_identifier: str
    identifier_type: str
    source: str | None


@dataclass(frozen=True, kw_only=True)
class RowOutcome:
    row_index: int
    status: RowStatus
    external_identifier: str
    batch_id: uuid.UUID | None = None
    resolved_batch_number: str | None = None
    created: bool = False
    conflict_batch_id: uuid.UUID | None = None
    conflict_batch_number: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class BulkAddBatchIdentifiersResult:
    outcomes: list[RowOutcome]
    counts: dict[str, int]


@dataclass(frozen=True, kw_only=True)
class BulkAddBatchIdentifiersCommand(Command):
    workspace_id: uuid.UUID
    importing_user_id: uuid.UUID
    source_default: str
    dry_run: bool
    rows: list[BulkIdentifierRow] = field(default_factory=list)


class BulkAddBatchIdentifiers:
    """Validates + optionally commits a bulk batch-identifier import."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        batch_repo: BatchRepository,
        settings_repo: WorkspaceSettingsRepository,
    ) -> None:
        self._uow = uow
        self._batch_repo = batch_repo
        self._settings_repo = settings_repo

    async def __call__(
        self, input: BulkAddBatchIdentifiersCommand
    ) -> Result[BulkAddBatchIdentifiersResult, DomainError]:
        async with self._uow:
            settings = await self._settings_repo.find_by_workspace_id(input.workspace_id)
            if settings is None:
                settings = WorkspaceSettings.create_default(workspace_id=input.workspace_id)
            width = settings.batch_sequence_width

            outcomes: list[RowOutcome] = []
            for row in input.rows:
                outcome = await self._process_row(
                    row=row,
                    workspace_id=input.workspace_id,
                    importing_user_id=input.importing_user_id,
                    source_default=input.source_default,
                    width=width,
                    dry_run=input.dry_run,
                )
                outcomes.append(outcome)

            if not input.dry_run:
                await self._uow.commit()

        counts = dict(Counter(o.status for o in outcomes))
        for key in ("resolved", "not_found", "conflict", "already_mapped", "error"):
            counts.setdefault(key, 0)

        return Success(BulkAddBatchIdentifiersResult(outcomes=outcomes, counts=counts))

    async def _process_row(
        self,
        *,
        row: BulkIdentifierRow,
        workspace_id: uuid.UUID,
        importing_user_id: uuid.UUID,
        source_default: str,
        width: int,
        dry_run: bool,
    ) -> RowOutcome:
        # 1. Resolve the Cellar batch reference.
        resolved_bn: str | None = None
        if row.cellar_batch_number:
            resolved_bn = row.cellar_batch_number
        elif row.cellar_molecule_reg_number and row.cellar_batch_sequence is not None:
            resolved_bn = f"{row.cellar_molecule_reg_number}-{row.cellar_batch_sequence:0{width}d}"
        else:
            return RowOutcome(
                row_index=row.row_index,
                status="error",
                external_identifier=row.external_identifier,
                message=(
                    "Row missing batch locator — provide either cellar_batch_number "
                    "OR (cellar_molecule_reg_number + cellar_batch_sequence)"
                ),
            )

        target = await self._batch_repo.find_by_batch_number(workspace_id, resolved_bn)
        if target is None:
            return RowOutcome(
                row_index=row.row_index,
                status="not_found",
                external_identifier=row.external_identifier,
                resolved_batch_number=resolved_bn,
            )

        # 2. Alias uniqueness check.
        existing_owner = await self._batch_repo.find_by_external_identifier(
            workspace_id, row.external_identifier
        )
        if existing_owner is not None:
            if existing_owner.id == target.id:
                return RowOutcome(
                    row_index=row.row_index,
                    status="already_mapped",
                    external_identifier=row.external_identifier,
                    batch_id=target.id,
                    resolved_batch_number=resolved_bn,
                )
            return RowOutcome(
                row_index=row.row_index,
                status="conflict",
                external_identifier=row.external_identifier,
                batch_id=target.id,
                resolved_batch_number=resolved_bn,
                conflict_batch_id=existing_owner.id,
                conflict_batch_number=existing_owner.batch_number.value,
            )

        # 3. If dry_run, just report resolved. Else attach + save.
        if not dry_run:
            target.add_identifier(
                BatchIdentifier.create(
                    batch_id=target.id,
                    identifier=row.external_identifier,
                    identifier_type=row.identifier_type,
                    source=row.source or source_default,
                    registered_by=importing_user_id,
                )
            )
            await self._batch_repo.save(target)

        return RowOutcome(
            row_index=row.row_index,
            status="resolved",
            external_identifier=row.external_identifier,
            batch_id=target.id,
            resolved_batch_number=resolved_bn,
            created=not dry_run,
        )
