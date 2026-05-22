"""CreateBatch use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from returns.pipeline import is_successful
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    MirrorSummary,
    SyncBatchIdentifierMirrors,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.workspace_config.custom_field_validator import CustomFieldValidator
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.shared.enums import AmountUnit, ConcentrationUnit
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError
from cellar.domain.shared.value_objects import Amount, Concentration
from cellar.domain.workspace_config.enums import FieldTarget
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings


@dataclass(frozen=True, kw_only=True)
class CreateBatchResult:
    """Wrapped result: created batch + summary of fan-out to identifier mirrors."""

    batch: Batch
    mirror_summary: MirrorSummary


@dataclass(frozen=True, kw_only=True)
class CreateBatchCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    source: str
    chemist: uuid.UUID
    amount_value: float
    amount_unit: str
    salt_entry_id: uuid.UUID | None = None
    salt_name: str | None = None
    salt_smiles: str | None = None
    salt_stoichiometry: int = 1
    formula_weight: float | None = None
    purity: float | None = None
    concentration_value: float | None = None
    concentration_unit: str | None = None
    supplier_org_id: uuid.UUID | None = None
    vendor_catalog_number: str | None = None
    vendor_lot_number: str | None = None
    synthesis_date: date | None = None
    expiry_date: date | None = None
    notebook_reference: str | None = None
    appearance: str | None = None
    custom_fields: dict[str, Any] | None = None


class CreateBatch:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: BatchRepository,
        molecule_repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
        custom_field_validator: CustomFieldValidator | None = None,
        workspace_settings_repo: WorkspaceSettingsRepository | None = None,
        sync: SyncBatchIdentifierMirrors | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._molecule_repo = molecule_repo
        self._dispatcher = dispatcher
        self._custom_field_validator = custom_field_validator
        self._workspace_settings_repo = workspace_settings_repo
        self._sync = sync

    async def _resolve_batch_width(self, workspace_id: uuid.UUID) -> int:
        if self._workspace_settings_repo is None:
            settings = WorkspaceSettings.create_default(workspace_id=workspace_id)
        else:
            settings = await self._workspace_settings_repo.find_by_workspace_id(
                workspace_id
            )
            if settings is None:
                settings = WorkspaceSettings.create_default(workspace_id=workspace_id)
        return settings.batch_sequence_width

    async def __call__(
        self, input: CreateBatchCommand, auth: AuthContext | None = None
    ) -> Result[CreateBatchResult, DomainError]:
        require_editor(auth)

        async with self._uow:
            # Validate molecule exists, belongs to workspace, and is not tombstoned
            molecule = await self._molecule_repo.find_by_id_in_workspace(
                input.workspace_id, input.molecule_id
            )
            if molecule is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))
            if molecule.is_tombstone:
                return Failure(ConflictError("Cannot create batch for a merged molecule"))

            width = await self._resolve_batch_width(input.workspace_id)
            batch_number = await self._repo.next_batch_number(
                input.workspace_id, input.molecule_id, width=width
            )
            concentration = None
            if input.concentration_value is not None and input.concentration_unit is not None:
                concentration = Concentration(
                    value=input.concentration_value,
                    unit=ConcentrationUnit(input.concentration_unit),
                )

            if self._custom_field_validator and input.custom_fields:
                validation = await self._custom_field_validator.validate(
                    input.custom_fields, FieldTarget.BATCH, input.workspace_id
                )
                if not is_successful(validation):
                    return Failure(validation.failure())

            batch = Batch.create(
                workspace_id=input.workspace_id,
                molecule_id=input.molecule_id,
                batch_number=batch_number,
                amount=Amount(value=input.amount_value, unit=AmountUnit(input.amount_unit)),
                source=BatchSource(input.source),
                chemist=input.chemist,
                salt_entry_id=input.salt_entry_id,
                salt_name=input.salt_name,
                salt_smiles=input.salt_smiles,
                salt_stoichiometry=input.salt_stoichiometry,
                formula_weight=input.formula_weight,
                purity=input.purity,
                concentration=concentration,
                supplier_org_id=input.supplier_org_id,
                vendor_catalog_number=input.vendor_catalog_number,
                vendor_lot_number=input.vendor_lot_number,
                synthesis_date=input.synthesis_date,
                expiry_date=input.expiry_date,
                notebook_reference=input.notebook_reference,
                appearance=input.appearance,
                custom_fields=input.custom_fields,
            )

            mirror_summary = MirrorSummary.empty()
            if self._sync is not None:
                mirror_summary = await self._sync.fan_out_for_new_batch(
                    workspace_id=input.workspace_id,
                    batch=batch,
                    identifiers=molecule.identifiers,
                    actor=input.chemist,
                )

            await self._repo.save(batch)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(CreateBatchResult(batch=batch, mirror_summary=mirror_summary))
