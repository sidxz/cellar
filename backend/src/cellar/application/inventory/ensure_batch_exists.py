"""EnsureBatchExists — resolve a batch reference, auto-create placeholder on miss.

Used by importers that need to attach data to a batch by external reference.
If the ref resolves (canonical or alias), returns the existing batch.
If both miss but the caller can prove which molecule the data belongs to,
creates a placeholder batch (source=EXTERNAL_REFERENCE, amount=0 mg,
chemist=importing_user) and captures the reference as an alias.

Subsequent imports referencing the same external ref hit the alias and
attach to the same placeholder, so the chemist can later fill in real
provenance.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.inventory.resolve_batch_ref import resolve_batch_ref
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    SyncBatchIdentifierMirrors,
)
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.errors import DomainError
from cellar.domain.shared.value_objects import Amount
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings


@dataclass(frozen=True, kw_only=True)
class EnsureBatchExistsCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    external_batch_ref: str
    importing_user_id: uuid.UUID
    source_label: str  # e.g. "CDD import 2026-05-21", "screening file run-NNN.csv"


@dataclass(frozen=True)
class EnsureBatchExistsOutcome:
    batch: Batch
    created: bool


class EnsureBatchExists:
    """Auto-resolve or auto-create a batch for an external reference."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        batch_repo: BatchRepository,
        settings_repo: WorkspaceSettingsRepository,
        sync: SyncBatchIdentifierMirrors | None = None,
        molecule_repo: MoleculeRepository | None = None,
    ) -> None:
        self._uow = uow
        self._batch_repo = batch_repo
        self._settings_repo = settings_repo
        self._sync = sync
        self._molecule_repo = molecule_repo

    async def __call__(
        self, input: EnsureBatchExistsCommand
    ) -> Result[EnsureBatchExistsOutcome, DomainError]:
        async with self._uow:
            existing = await resolve_batch_ref(
                self._batch_repo, input.workspace_id, input.external_batch_ref
            )
            if existing is not None:
                # If the alias didn't already exist on the batch, attach it.
                has_alias = any(
                    i.identifier == input.external_batch_ref for i in existing.identifiers
                )
                if not has_alias:
                    existing.add_identifier(BatchIdentifier.create(
                        batch_id=existing.id,
                        identifier=input.external_batch_ref,
                        identifier_type="external_lot",
                        source=input.source_label,
                        registered_by=input.importing_user_id,
                    ))
                    await self._batch_repo.save(existing)
                    await self._uow.commit()
                return Success(EnsureBatchExistsOutcome(batch=existing, created=False))

            # MISS: auto-create placeholder
            settings = await self._settings_repo.find_by_workspace_id(input.workspace_id)
            if settings is None:
                settings = WorkspaceSettings.create_default(workspace_id=input.workspace_id)
            width = settings.batch_sequence_width

            batch_number = await self._batch_repo.next_batch_number(
                input.workspace_id, input.molecule_id, width=width
            )
            batch = Batch.create(
                workspace_id=input.workspace_id,
                molecule_id=input.molecule_id,
                batch_number=batch_number,
                amount=Amount(value=0.0, unit=AmountUnit.MG),
                source=BatchSource.EXTERNAL_REFERENCE,
                chemist=input.importing_user_id,
            )
            batch.add_identifier(BatchIdentifier.create(
                batch_id=batch.id,
                identifier=input.external_batch_ref,
                identifier_type="external_lot",
                source=input.source_label,
                registered_by=input.importing_user_id,
            ))

            if self._sync is not None and self._molecule_repo is not None:
                mol = await self._molecule_repo.find_by_id_in_workspace(
                    input.workspace_id, input.molecule_id
                )
                if mol is not None and mol.identifiers:
                    await self._sync.fan_out_for_new_batch(
                        workspace_id=input.workspace_id,
                        batch=batch,
                        identifiers=mol.identifiers,
                        actor=input.importing_user_id,
                    )

            await self._batch_repo.save(batch)
            await self._uow.commit()

        return Success(EnsureBatchExistsOutcome(batch=batch, created=True))
