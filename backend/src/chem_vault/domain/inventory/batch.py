"""Batch aggregate root — a specific physical preparation of a molecule."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from chem_vault.domain.inventory.enums import BatchSource
from chem_vault.domain.inventory.events import BatchCreated, BatchReassigned
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import Amount, BatchNumber, Concentration, StorageCondition


class Batch(AggregateRoot):
    """A specific physical preparation of a molecule.

    Invariants:
        - batch_number is immutable after creation
        - purity in (0, 100] if set
        - amount is non-negative
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        molecule_id: uuid.UUID,
        batch_number: BatchNumber,
        salt_entry_id: uuid.UUID | None = None,
        salt_name: str | None = None,
        salt_smiles: str | None = None,
        salt_stoichiometry: int = 1,
        formula_weight: float | None = None,
        purity: float | None = None,
        amount: Amount,
        concentration: Concentration | None = None,
        source: BatchSource,
        supplier_org_id: uuid.UUID | None = None,
        vendor_catalog_number: str | None = None,
        vendor_lot_number: str | None = None,
        chemist: uuid.UUID,
        synthesis_date: date | None = None,
        expiry_date: date | None = None,
        notebook_reference: str | None = None,
        storage_conditions: StorageCondition | None = None,
        storage_conditions_notes: str | None = None,
        appearance: str | None = None,
        custom_fields: dict[str, Any] | None = None,
        synthesis_route_id: uuid.UUID | None = None,
        synthesis_step_id: uuid.UUID | None = None,
        synthesis_request_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)

        if purity is not None and not (0 < purity <= 100):
            raise ValidationError("Purity must be in range (0, 100]")

        self.workspace_id = workspace_id
        self.molecule_id = molecule_id
        self._batch_number = batch_number
        self.salt_entry_id = salt_entry_id
        self.salt_name = salt_name
        self.salt_smiles = salt_smiles
        self.salt_stoichiometry = salt_stoichiometry
        self.formula_weight = formula_weight
        self.purity = purity
        self.amount = amount
        self.concentration = concentration
        self.source = source
        self.supplier_org_id = supplier_org_id
        self.vendor_catalog_number = vendor_catalog_number
        self.vendor_lot_number = vendor_lot_number
        self.chemist = chemist
        self.synthesis_date = synthesis_date
        self.expiry_date = expiry_date
        self.notebook_reference = notebook_reference
        self.storage_conditions = storage_conditions
        self.storage_conditions_notes = storage_conditions_notes
        self.appearance = appearance
        self.custom_fields = custom_fields
        self.synthesis_route_id = synthesis_route_id
        self.synthesis_step_id = synthesis_step_id
        self.synthesis_request_id = synthesis_request_id

    @property
    def batch_number(self) -> BatchNumber:
        return self._batch_number

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        molecule_id: uuid.UUID,
        batch_number: BatchNumber,
        amount: Amount,
        source: BatchSource,
        chemist: uuid.UUID,
        salt_entry_id: uuid.UUID | None = None,
        salt_name: str | None = None,
        salt_smiles: str | None = None,
        salt_stoichiometry: int = 1,
        formula_weight: float | None = None,
        purity: float | None = None,
        concentration: Concentration | None = None,
        supplier_org_id: uuid.UUID | None = None,
        vendor_catalog_number: str | None = None,
        vendor_lot_number: str | None = None,
        synthesis_date: date | None = None,
        expiry_date: date | None = None,
        notebook_reference: str | None = None,
        storage_conditions: StorageCondition | None = None,
        storage_conditions_notes: str | None = None,
        appearance: str | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> Batch:
        batch = cls(
            workspace_id=workspace_id,
            molecule_id=molecule_id,
            batch_number=batch_number,
            amount=amount,
            source=source,
            chemist=chemist,
            salt_entry_id=salt_entry_id,
            salt_name=salt_name,
            salt_smiles=salt_smiles,
            salt_stoichiometry=salt_stoichiometry,
            formula_weight=formula_weight,
            purity=purity,
            concentration=concentration,
            supplier_org_id=supplier_org_id,
            vendor_catalog_number=vendor_catalog_number,
            vendor_lot_number=vendor_lot_number,
            synthesis_date=synthesis_date,
            expiry_date=expiry_date,
            notebook_reference=notebook_reference,
            storage_conditions=storage_conditions,
            storage_conditions_notes=storage_conditions_notes,
            appearance=appearance,
            custom_fields=custom_fields,
        )
        batch.register_event(
            BatchCreated(
                aggregate_id=batch.id,
                aggregate_type="Batch",
                workspace_id=workspace_id,
                molecule_id=molecule_id,
                batch_number=batch_number.value,
                source=source.value,
                supplier_org_id=supplier_org_id,
            )
        )
        return batch

    # ------------------------------------------------------------------
    # Merge support
    # ------------------------------------------------------------------

    def reassign_to_molecule(
        self, *, new_molecule_id: uuid.UUID, merge_event_id: uuid.UUID
    ) -> None:
        """Reassign this batch to a different molecule during merge."""
        old_id = self.molecule_id
        self.molecule_id = new_molecule_id
        self.updated_at = datetime.now(UTC)
        self.register_event(
            BatchReassigned(
                aggregate_id=self.id,
                aggregate_type="Batch",
                workspace_id=self.workspace_id,
                old_molecule_id=old_id,
                new_molecule_id=new_molecule_id,
                merge_event_id=merge_event_id,
            )
        )

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def update_amount(self, amount: Amount) -> None:
        self.amount = amount
        self.updated_at = datetime.now(UTC)

    def update_purity(self, purity: float | None) -> None:
        if purity is not None and not (0 < purity <= 100):
            raise ValidationError("Purity must be in range (0, 100]")
        self.purity = purity
        self.updated_at = datetime.now(UTC)

    def update(
        self,
        *,
        salt_entry_id: uuid.UUID | None = ...,  # type: ignore[assignment]
        salt_name: str | None = ...,  # type: ignore[assignment]
        salt_smiles: str | None = ...,  # type: ignore[assignment]
        salt_stoichiometry: int = ...,  # type: ignore[assignment]
        formula_weight: float | None = ...,  # type: ignore[assignment]
        purity: float | None = ...,  # type: ignore[assignment]
        amount: Amount | None = None,
        concentration: Concentration | None = ...,  # type: ignore[assignment]
        appearance: str | None = ...,  # type: ignore[assignment]
        expiry_date: date | None = ...,  # type: ignore[assignment]
        notebook_reference: str | None = ...,  # type: ignore[assignment]
        storage_conditions: StorageCondition | None = ...,  # type: ignore[assignment]
        storage_conditions_notes: str | None = ...,  # type: ignore[assignment]
        custom_fields: dict[str, Any] | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields. Uses sentinel ``...`` for optional nullable fields."""
        if purity is not ...:
            if purity is not None and not (0 < purity <= 100):
                raise ValidationError("Purity must be in range (0, 100]")
            self.purity = purity
        if salt_entry_id is not ...:
            self.salt_entry_id = salt_entry_id
        if salt_name is not ...:
            self.salt_name = salt_name
        if salt_smiles is not ...:
            self.salt_smiles = salt_smiles
        if salt_stoichiometry is not ...:
            self.salt_stoichiometry = salt_stoichiometry
        if formula_weight is not ...:
            self.formula_weight = formula_weight
        if amount is not None:
            self.amount = amount
        if concentration is not ...:
            self.concentration = concentration
        if appearance is not ...:
            self.appearance = appearance
        if expiry_date is not ...:
            self.expiry_date = expiry_date
        if notebook_reference is not ...:
            self.notebook_reference = notebook_reference
        if storage_conditions is not ...:
            self.storage_conditions = storage_conditions
        if storage_conditions_notes is not ...:
            self.storage_conditions_notes = storage_conditions_notes
        if custom_fields is not ...:
            self.custom_fields = custom_fields
        self.updated_at = datetime.now(UTC)
