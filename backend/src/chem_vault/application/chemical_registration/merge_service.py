"""MergeService — orchestrates molecule merge operations.

Validates both molecules, creates a snapshot + MergeEvent, transfers the
source's registration number as a legacy identifier on the target, runs
side-effect handlers (so external BCs can relocate their data), and marks
the source as a tombstone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.chemical_registration.merge_side_effect_registry import (
    MergeSideEffectRegistry,
)
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.enums import IdentifierType, MergeReason
from chem_vault.domain.chemical_registration.merge_event import MergeEvent
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from chem_vault.domain.chemical_registration.repository import (
    MergeEventRepository,
    MoleculeRepository,
)
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class MergeCommand(Command):
    """Input for a molecule merge operation."""

    source_molecule_id: uuid.UUID
    target_molecule_id: uuid.UUID
    reason: MergeReason
    merged_by: uuid.UUID
    disclosure_request_id: uuid.UUID | None = None
    notes: str | None = None


def _build_snapshot(molecule: Molecule) -> dict:
    """Create a JSON-serialisable snapshot of the source molecule state."""
    return {
        "registration_number": molecule.registration_number.value,
        "name": molecule.name,
        "molecule_type": molecule.molecule_type.value,
        "structure_status": molecule.structure_status.value,
        "identifiers": [
            {"identifier": ident.identifier, "type": ident.identifier_type.value}
            for ident in molecule.identifiers
        ],
        "tags": list(molecule.tags),
    }


class MergeService:
    """Application service that orchestrates a molecule merge."""

    def __init__(
        self,
        uow: UnitOfWork,
        molecule_repo: MoleculeRepository,
        merge_event_repo: MergeEventRepository,
        dispatcher: EventDispatcherProtocol,
        side_effect_registry: MergeSideEffectRegistry,
    ) -> None:
        self._uow = uow
        self._molecule_repo = molecule_repo
        self._merge_event_repo = merge_event_repo
        self._dispatcher = dispatcher
        self._side_effect_registry = side_effect_registry

    async def __call__(
        self,
        input: MergeCommand,
        auth: AuthContext | None = None,
    ) -> Result[MergeEvent, DomainError]:
        """Execute a molecule merge.

        Returns ``Success(MergeEvent)`` or ``Failure(DomainError)``.
        Raises ``AuthorizationError`` if the caller lacks editor role.
        """
        require_editor(auth)

        # --- Guard: self-merge ---
        if input.source_molecule_id == input.target_molecule_id:
            return Failure(ValidationError("A molecule cannot be merged into itself"))

        async with self._uow:
            # --- Load aggregates ---
            source = await self._molecule_repo.find_by_id(input.source_molecule_id)
            if source is None:
                return Failure(
                    NotFoundError("Molecule", str(input.source_molecule_id))
                )

            target = await self._molecule_repo.find_by_id(input.target_molecule_id)
            if target is None:
                return Failure(
                    NotFoundError("Molecule", str(input.target_molecule_id))
                )

            # --- Guard: tombstones ---
            if source.is_tombstone:
                return Failure(
                    ConflictError("Source molecule is already a tombstone")
                )
            if target.is_tombstone:
                return Failure(
                    ConflictError("Target molecule is already a tombstone")
                )

            # --- Snapshot ---
            snapshot = _build_snapshot(source)

            # --- Create MergeEvent ---
            merge_event = MergeEvent.create(
                source_molecule_id=source.id,
                target_molecule_id=target.id,
                reason=input.reason,
                merged_by=input.merged_by,
                snapshot=snapshot,
                disclosure_request_id=input.disclosure_request_id,
                notes=input.notes,
            )
            await self._merge_event_repo.save(merge_event)

            # --- Transfer ALL identifiers from source to target ---
            target_ident_values = {i.identifier for i in target.identifiers}
            reg_value = source.registration_number.value

            # 1. Registration number as internal_legacy
            if reg_value not in target_ident_values:
                target.add_identifier(
                    MoleculeIdentifier.create(
                        molecule_id=target.id,
                        identifier=reg_value,
                        identifier_type=IdentifierType.INTERNAL_LEGACY,
                        source=f"Merge from {reg_value}",
                        registered_by=input.merged_by,
                    )
                )
                target_ident_values.add(reg_value)

            # 2. All other source identifiers (vendor_id, cas, custom, etc.)
            for source_ident in source.identifiers:
                if source_ident.identifier not in target_ident_values:
                    target.add_identifier(
                        MoleculeIdentifier.create(
                            molecule_id=target.id,
                            identifier=source_ident.identifier,
                            identifier_type=source_ident.identifier_type,
                            source=f"Merge transfer from {reg_value}",
                            registered_by=input.merged_by,
                        )
                    )
                    target_ident_values.add(source_ident.identifier)

            # 3. Clear source identifiers BEFORE tombstoning to avoid
            #    UNIQUE(workspace_id, identifier) constraint violation.
            source.clear_identifiers()

            # --- Side effects (e.g., re-point Batch FKs) ---
            await self._side_effect_registry.execute_all(
                self._uow.session,  # type: ignore[arg-type]
                source.id,
                target.id,
            )

            # --- Mark source as tombstone ---
            source.mark_as_tombstone(
                merged_into_id=target.id,
                merge_event_id=merge_event.id,
                reason=input.reason.value,
            )

            # --- Persist & dispatch ---
            await self._molecule_repo.save(source)
            await self._molecule_repo.save(target)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

            return Success(merge_event)
