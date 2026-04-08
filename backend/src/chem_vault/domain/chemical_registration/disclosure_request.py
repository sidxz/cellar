"""DisclosureRequest aggregate root — formal workflow for disclosing an undisclosed molecule."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.chemical_registration.enums import (
    DisclosureResolutionType,
    DisclosureStatus,
)
from chem_vault.domain.chemical_registration.events import (
    DisclosureConflict,
    DisclosureRequested,
    DisclosureResolved,
)
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError

# ---------------------------------------------------------------------------
# State-machine transition table
# ---------------------------------------------------------------------------

_DISCLOSURE_TRANSITIONS: dict[DisclosureStatus, set[DisclosureStatus]] = {
    DisclosureStatus.PENDING: {DisclosureStatus.PROCESSING, DisclosureStatus.REJECTED},
    DisclosureStatus.PROCESSING: {
        DisclosureStatus.DISCLOSED,
        DisclosureStatus.MERGED,
        DisclosureStatus.CONFLICT,
    },
    DisclosureStatus.DISCLOSED: set(),
    DisclosureStatus.MERGED: set(),
    DisclosureStatus.CONFLICT: {
        DisclosureStatus.REJECTED,
        DisclosureStatus.MERGED,
        DisclosureStatus.DISCLOSED,
    },
    DisclosureStatus.REJECTED: set(),
}


class DisclosureRequest(AggregateRoot):
    """A formal request to disclose the structure of an undisclosed molecule.

    State machine::

        pending -> processing -> disclosed   (no InChIKey match)
        pending -> processing -> merged      (InChIKey matched existing)
        pending -> processing -> conflict    (needs manual review)
        pending -> rejected                  (invalid SMILES / admin rejected)
        conflict -> rejected                 (admin rejects conflict)
        conflict -> merged                   (admin accepts merge resolution)
        conflict -> disclosed                (admin accepts as new structure)
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        bulk_disclosure_id: uuid.UUID | None = None,
        molecule_id: uuid.UUID,
        disclosed_smiles: str,
        canonical_smiles: str | None = None,
        inchi_key: str | None = None,
        status: DisclosureStatus = DisclosureStatus.PENDING,
        resolution_type: DisclosureResolutionType | None = None,
        resolved_to_molecule_id: uuid.UUID | None = None,
        disclosing_org_id: uuid.UUID | None = None,
        requested_by: uuid.UUID,
        requested_at: datetime | None = None,
        resolved_at: datetime | None = None,
        conflict_reason: str | None = None,
        notes: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)

        if not disclosed_smiles or not disclosed_smiles.strip():
            raise ValidationError("disclosed_smiles must not be empty")

        self.workspace_id = workspace_id
        self.bulk_disclosure_id = bulk_disclosure_id
        self.molecule_id = molecule_id
        self.disclosed_smiles = disclosed_smiles.strip()
        self.canonical_smiles = canonical_smiles
        self.inchi_key = inchi_key
        self.status = status
        self.resolution_type = resolution_type
        self.resolved_to_molecule_id = resolved_to_molecule_id
        self.disclosing_org_id = disclosing_org_id
        self.requested_by = requested_by
        self.requested_at = requested_at or datetime.now(UTC)
        self.resolved_at = resolved_at
        self.conflict_reason = conflict_reason
        self.notes = notes

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        molecule_id: uuid.UUID,
        disclosed_smiles: str,
        requested_by: uuid.UUID,
        disclosing_org_id: uuid.UUID | None = None,
        bulk_disclosure_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> DisclosureRequest:
        """Create a new disclosure request in PENDING status."""
        req = cls(
            workspace_id=workspace_id,
            molecule_id=molecule_id,
            disclosed_smiles=disclosed_smiles,
            requested_by=requested_by,
            disclosing_org_id=disclosing_org_id,
            bulk_disclosure_id=bulk_disclosure_id,
            notes=notes,
        )
        req.register_event(
            DisclosureRequested(
                aggregate_id=req.id,
                aggregate_type="DisclosureRequest",
                molecule_id=molecule_id,
                disclosing_org_id=disclosing_org_id,
            )
        )
        return req

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _guard_transition(self, target: DisclosureStatus) -> None:
        """Validate the state transition is allowed."""
        allowed = _DISCLOSURE_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition disclosure status from "
                f"'{self.status}' to '{target}'"
            )

    def start_processing(self) -> None:
        """PENDING -> PROCESSING."""
        self._guard_transition(DisclosureStatus.PROCESSING)
        self.status = DisclosureStatus.PROCESSING
        self.updated_at = datetime.now(UTC)

    def resolve_as_new_structure(
        self,
        *,
        canonical_smiles: str,
        inchi_key: str,
    ) -> None:
        """PROCESSING -> DISCLOSED (no InChIKey match, new structure)."""
        self._guard_transition(DisclosureStatus.DISCLOSED)
        self.status = DisclosureStatus.DISCLOSED
        self.canonical_smiles = canonical_smiles
        self.inchi_key = inchi_key
        self.resolution_type = DisclosureResolutionType.NEW_STRUCTURE
        self.resolved_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.register_event(
            DisclosureResolved(
                aggregate_id=self.id,
                aggregate_type="DisclosureRequest",
                resolution_type=DisclosureResolutionType.NEW_STRUCTURE.value,
                resolved_to_molecule_id=None,
            )
        )

    def resolve_as_merged(
        self,
        *,
        canonical_smiles: str,
        inchi_key: str,
        resolved_to_molecule_id: uuid.UUID,
    ) -> None:
        """PROCESSING -> MERGED (InChIKey matched existing molecule)."""
        self._guard_transition(DisclosureStatus.MERGED)
        self.status = DisclosureStatus.MERGED
        self.canonical_smiles = canonical_smiles
        self.inchi_key = inchi_key
        self.resolution_type = DisclosureResolutionType.MERGED_INTO_EXISTING
        self.resolved_to_molecule_id = resolved_to_molecule_id
        self.resolved_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.register_event(
            DisclosureResolved(
                aggregate_id=self.id,
                aggregate_type="DisclosureRequest",
                resolution_type=DisclosureResolutionType.MERGED_INTO_EXISTING.value,
                resolved_to_molecule_id=resolved_to_molecule_id,
            )
        )

    def mark_conflict(self, *, reason: str) -> None:
        """PROCESSING -> CONFLICT (needs manual review)."""
        self._guard_transition(DisclosureStatus.CONFLICT)
        self.status = DisclosureStatus.CONFLICT
        self.conflict_reason = reason
        self.updated_at = datetime.now(UTC)
        self.register_event(
            DisclosureConflict(
                aggregate_id=self.id,
                aggregate_type="DisclosureRequest",
                conflict_reason=reason,
            )
        )

    def reject(self, *, reason: str) -> None:
        """PENDING|CONFLICT -> REJECTED."""
        self._guard_transition(DisclosureStatus.REJECTED)
        self.status = DisclosureStatus.REJECTED
        self.conflict_reason = reason
        self.resolved_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
