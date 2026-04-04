"""DisclosureService — orchestrates the disclosure of an undisclosed molecule.

Coordinates structure processing, dedup via InChIKey, and delegates to
MergeService when the disclosed structure matches an existing molecule.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.chemical_registration.merge_service import MergeCommand, MergeService
from chem_vault.application.chemical_registration.protocols import StructureProcessorProtocol
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.disclosure_request import DisclosureRequest
from chem_vault.domain.chemical_registration.enums import MergeReason, StructureStatus
from chem_vault.domain.chemical_registration.repository import (
    DisclosureRequestRepository,
    MoleculeRepository,
)
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError


# ---------------------------------------------------------------------------
# Command & outcome DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class SubmitDisclosureCommand(Command):
    """Input for disclosing an undisclosed molecule's structure."""

    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    disclosed_smiles: str
    requested_by: uuid.UUID
    disclosing_org_id: uuid.UUID | None = None
    notes: str | None = None


@dataclass(frozen=True)
class DisclosureOutcome:
    """Result of a successful disclosure submission."""

    disclosure_request: DisclosureRequest
    was_merged: bool
    merged_into_molecule_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DisclosureService:
    """Application service that orchestrates molecule disclosure.

    Flow:
    1. Validate auth + load molecule (must be undisclosed, not tombstone).
    2. Create ``DisclosureRequest`` and move to PROCESSING.
    3. Process SMILES via ``StructureProcessorProtocol``.
    4. Check InChIKey against existing disclosed molecules.
    5a. **No match** -- disclose the molecule in-place, resolve as new.
    5b. **Match found** -- resolve as merged, delegate to ``MergeService``.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        molecule_repo: MoleculeRepository,
        disclosure_repo: DisclosureRequestRepository,
        structure_processor: StructureProcessorProtocol,
        merge_service: MergeService,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._molecule_repo = molecule_repo
        self._disclosure_repo = disclosure_repo
        self._structure_processor = structure_processor
        self._merge_service = merge_service
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: SubmitDisclosureCommand,
        auth: AuthContext | None = None,
    ) -> Result[DisclosureOutcome, DomainError]:
        """Execute disclosure workflow.

        Returns ``Success(DisclosureOutcome)`` or ``Failure(DomainError)``.
        Raises ``AuthorizationError`` if caller lacks editor role.
        """
        require_editor(auth)

        async with self._uow:
            # --- Load & validate molecule ---
            molecule = await self._molecule_repo.find_by_id(input.molecule_id)
            if molecule is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            if molecule.workspace_id != input.workspace_id:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            if molecule.is_tombstone:
                return Failure(ConflictError("Cannot disclose a tombstoned molecule"))

            if molecule.structure_status != StructureStatus.UNDISCLOSED:
                return Failure(
                    ValidationError("Only undisclosed molecules can be disclosed")
                )

            # --- Create disclosure request ---
            dr = DisclosureRequest.create(
                molecule_id=input.molecule_id,
                disclosed_smiles=input.disclosed_smiles,
                requested_by=input.requested_by,
                disclosing_org_id=input.disclosing_org_id,
                notes=input.notes,
            )
            dr.start_processing()

            # --- Process SMILES ---
            process_result = self._structure_processor.process(input.disclosed_smiles)
            if not process_result.is_success:
                # Reject disclosure if structure processing fails
                reason = str(process_result.failure())
                dr.reject(reason=reason)
                await self._disclosure_repo.save(dr)
                events = await self._uow.commit()
                await self._dispatcher.dispatch_all(events)
                return Failure(
                    ValidationError(f"Structure processing failed: {reason}")
                )

            processed = process_result.unwrap()
            canonical_smiles = processed.structure.smiles
            inchi_key = processed.structure.inchi_key

            # --- Check for existing molecule with same InChIKey ---
            existing = await self._molecule_repo.find_by_inchi_key(
                input.workspace_id, inchi_key
            )

            if existing is None:
                # ---- Path A: new structure ----
                molecule.disclose(
                    structure=processed.structure,
                    descriptors=processed.descriptors,
                    disclosed_by=input.requested_by,
                )
                dr.resolve_as_new_structure(
                    canonical_smiles=canonical_smiles,
                    inchi_key=inchi_key,
                )

                await self._molecule_repo.save(molecule)
                await self._disclosure_repo.save(dr)
                events = await self._uow.commit()
                await self._dispatcher.dispatch_all(events)

                return Success(
                    DisclosureOutcome(
                        disclosure_request=dr,
                        was_merged=False,
                    )
                )

            # ---- Path B: merge needed ----
            # Save DR in PROCESSING state — only resolve after merge succeeds.
            # This avoids an inconsistent state if the merge fails.
            await self._disclosure_repo.save(dr)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

            target_molecule_id = existing.id

        # Delegate merge to MergeService (opens its own UoW)
        merge_result = await self._merge_service(
            MergeCommand(
                source_molecule_id=input.molecule_id,
                target_molecule_id=target_molecule_id,
                reason=MergeReason.DISCLOSURE_RESOLVED,
                merged_by=input.requested_by,
                disclosure_request_id=dr.id,
                notes=input.notes,
            ),
            auth=auth,
        )

        # Update DR status based on merge outcome in a separate transaction
        async with self._uow:
            loaded_dr = await self._disclosure_repo.find_by_id(dr.id)
            if loaded_dr is None:
                return Failure(NotFoundError("DisclosureRequest", str(dr.id)))

            if merge_result.is_success:
                loaded_dr.resolve_as_merged(
                    canonical_smiles=canonical_smiles,
                    inchi_key=inchi_key,
                    resolved_to_molecule_id=target_molecule_id,
                )
            else:
                loaded_dr.mark_conflict(
                    f"Merge failed: {merge_result.failure().message}"
                )

            await self._disclosure_repo.save(loaded_dr)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

        if not merge_result.is_success:
            return Failure(merge_result.failure())

        return Success(
            DisclosureOutcome(
                disclosure_request=loaded_dr,
                was_merged=True,
                merged_into_molecule_id=target_molecule_id,
            )
        )
