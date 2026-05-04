"""SaltEntry aggregate — domain model for workspace-scoped salt catalog entries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.events import SaltEntryCreated, SaltEntryUpdated

__all__ = ["SaltEntry", "SaltEntryCreated", "SaltEntryUpdated"]

# Sentinel for "not provided" in update()
UNSET = object()


class SaltEntry(AggregateRoot):
    """Aggregate root for a workspace-scoped salt catalog entry.

    A SaltEntry describes a salt or counter-ion used during chemical registration
    to strip and account for salt forms (e.g. HCl, Na, TFA). Each entry holds the
    SMILES representation and molecular weight needed for parent extraction and
    formula correction.

    System-seeded entries (is_default=True) cannot be deleted.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        code: str,
        name: str,
        smiles: str,
        molecular_weight: float,
        is_default: bool = False,
        is_active: bool = True,
        version: int = 1,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(
            id=id,
            version=version,
            created_at=created_at,
            updated_at=updated_at,
        )
        self.workspace_id = workspace_id
        self.code = code
        self.name = name
        self.smiles = smiles
        self.molecular_weight = molecular_weight
        self.is_default = is_default
        self.is_active = is_active

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        code: str,
        name: str,
        smiles: str,
        molecular_weight: float,
        is_default: bool = False,
    ) -> SaltEntry:
        """Create and validate a new SaltEntry."""
        if not code or not code.strip():
            raise ValidationError("code must not be empty")
        if not name or not name.strip():
            raise ValidationError("name must not be empty")
        if not smiles or not smiles.strip():
            raise ValidationError("smiles must not be empty")
        if molecular_weight <= 0:
            raise ValidationError("molecular_weight must be greater than 0")

        entry = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            code=code.strip(),
            name=name.strip(),
            smiles=smiles.strip(),
            molecular_weight=molecular_weight,
            is_default=is_default,
        )
        entry.register_event(
            SaltEntryCreated(
                aggregate_id=entry.id,
                aggregate_type="SaltEntry",
                workspace_id=workspace_id,
                code=code.strip(),
            )
        )
        return entry

    # ------------------------------------------------------------------
    # Mutation commands
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        name: str | object = UNSET,
        smiles: str | object = UNSET,
        molecular_weight: float | object = UNSET,
    ) -> None:
        """Partial update — only provided fields are changed."""
        if name is not UNSET:
            name_str = str(name).strip()
            if not name_str:
                raise ValidationError("name must not be empty")
            self.name = name_str
        if smiles is not UNSET:
            smiles_str = str(smiles).strip()
            if not smiles_str:
                raise ValidationError("smiles must not be empty")
            self.smiles = smiles_str
        if molecular_weight is not UNSET:
            mw = float(molecular_weight)  # type: ignore[arg-type]
            if mw <= 0:
                raise ValidationError("molecular_weight must be greater than 0")
            self.molecular_weight = mw

        self.updated_at = datetime.now(UTC)
        self.register_event(
            SaltEntryUpdated(
                aggregate_id=self.id,
                aggregate_type="SaltEntry",
                workspace_id=self.workspace_id,
            )
        )

    def deactivate(self) -> None:
        """Mark this salt entry as inactive (soft-disable)."""
        self.is_active = False
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SaltEntryUpdated(
                aggregate_id=self.id,
                aggregate_type="SaltEntry",
                workspace_id=self.workspace_id,
            )
        )

    def activate(self) -> None:
        """Re-enable a previously deactivated salt entry."""
        self.is_active = True
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SaltEntryUpdated(
                aggregate_id=self.id,
                aggregate_type="SaltEntry",
                workspace_id=self.workspace_id,
            )
        )
