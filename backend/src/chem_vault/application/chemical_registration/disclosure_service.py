"""DisclosureService — orchestrates the disclosure of an undisclosed molecule.

Coordinates structure processing, dedup via InChIKey, and delegates to
MergeService when the disclosed structure matches an existing molecule.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success  # noqa: F401 (Failure used in isinstance checks)

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
    scientist_name: str | None = None
    auto_approve: bool = True
    notes: str | None = None


@dataclass(frozen=True)
class DisclosureOutcome:
    """Result of a successful disclosure submission."""

    disclosure_request: DisclosureRequest
    was_merged: bool
    merged_into_molecule_id: uuid.UUID | None = None
    needs_confirmation: bool = False
    matched_molecule_id: uuid.UUID | None = None


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

        # --- Process SMILES before opening the UoW (pure computation) ---
        process_result = self._structure_processor.process(input.disclosed_smiles)

        # --- Single UoW: validate, mutate, commit ---
        merge_failure: DomainError | None = None
        outcome: DisclosureOutcome | None = None
        events: list = []

        async with self._uow:
            # 1. Load and validate molecule
            molecule = await self._molecule_repo.find_by_id_in_workspace(
                input.workspace_id, input.molecule_id
            )
            if molecule is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            if molecule.is_tombstone:
                return Failure(ConflictError("Cannot disclose a tombstoned molecule"))

            if molecule.structure_status != StructureStatus.UNDISCLOSED:
                return Failure(
                    ValidationError("Only undisclosed molecules can be disclosed")
                )

            # 2. Create disclosure request and move to PROCESSING
            dr = DisclosureRequest.create(
                workspace_id=input.workspace_id,
                molecule_id=input.molecule_id,
                disclosed_smiles=input.disclosed_smiles,
                requested_by=input.requested_by,
                disclosing_org_id=input.disclosing_org_id,
                scientist_name=input.scientist_name,
                notes=input.notes,
            )
            dr.start_processing()

            # 3. Handle structure processing failure
            if isinstance(process_result, Failure):
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

            # 4. Check for existing molecule with same InChIKey
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
                outcome = DisclosureOutcome(
                    disclosure_request=dr,
                    was_merged=False,
                )

            elif not input.auto_approve:
                # ---- Path B1: merge needed, pause for confirmation ----
                target_molecule_id = existing.id
                dr.mark_pending_confirmation(
                    canonical_smiles=canonical_smiles,
                    inchi_key=inchi_key,
                    matched_molecule_id=target_molecule_id,
                )
                await self._disclosure_repo.save(dr)
                events = await self._uow.commit()
                outcome = DisclosureOutcome(
                    disclosure_request=dr,
                    was_merged=False,
                    needs_confirmation=True,
                    matched_molecule_id=target_molecule_id,
                )

            else:
                # ---- Path B2: merge needed, auto-approve ----
                target_molecule_id = existing.id

                # Execute merge within the SAME transaction for atomicity.
                # Save the disclosure request FIRST so the FK from
                # merge_events.disclosure_request_id is satisfiable.
                await self._disclosure_repo.save(dr)

                merge_result = await self._merge_service.merge_in_transaction(
                    MergeCommand(
                        workspace_id=input.workspace_id,
                        source_molecule_id=input.molecule_id,
                        target_molecule_id=target_molecule_id,
                        reason=MergeReason.DISCLOSURE_RESOLVED,
                        merged_by=input.requested_by,
                        disclosure_request_id=dr.id,
                        notes=input.notes,
                    ),
                )

                if isinstance(merge_result, Success):
                    dr.resolve_as_merged(
                        canonical_smiles=canonical_smiles,
                        inchi_key=inchi_key,
                        resolved_to_molecule_id=target_molecule_id,
                    )
                else:
                    dr.mark_conflict(
                        reason=f"Merge failed: {merge_result.failure().message}"
                    )

                await self._disclosure_repo.save(dr)
                events = await self._uow.commit()

                if isinstance(merge_result, Failure):
                    merge_failure = merge_result.failure()
                else:
                    outcome = DisclosureOutcome(
                        disclosure_request=dr,
                        was_merged=True,
                        merged_into_molecule_id=target_molecule_id,
                    )

        await self._dispatcher.dispatch_all(events)

        if merge_failure is not None:
            return Failure(merge_failure)

        assert outcome is not None  # merge_failure guard above ensures this
        return Success(outcome)
