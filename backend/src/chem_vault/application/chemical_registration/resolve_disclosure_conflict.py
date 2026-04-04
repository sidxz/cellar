"""ResolveDisclosureConflict command — resolve a disclosure stuck in CONFLICT status."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.chemical_registration.merge_service import MergeCommand, MergeService
from chem_vault.application.chemical_registration.protocols import StructureProcessorProtocol
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.disclosure_request import DisclosureRequest
from chem_vault.domain.chemical_registration.enums import DisclosureStatus, MergeReason
from chem_vault.domain.chemical_registration.repository import (
    DisclosureRequestRepository,
    MoleculeRepository,
)
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError


class ConflictResolution(StrEnum):
    REJECT = "reject"
    ACCEPT_MERGE = "accept_merge"
    ACCEPT_AS_NEW = "accept_as_new"


@dataclass(frozen=True, kw_only=True)
class ResolveConflictCommand(Command):
    workspace_id: uuid.UUID
    disclosure_id: uuid.UUID
    resolution: str
    reason: str | None = None
    resolved_by: uuid.UUID


class ResolveDisclosureConflict:
    """Command use case: resolve a disclosure request in CONFLICT status.

    Resolutions:
    - reject: reject the disclosure, no further action
    - accept_merge: accept the merge into the matched molecule
    - accept_as_new: disclose the molecule as a new structure in-place
    """

    def __init__(
        self,
        uow: UnitOfWork,
        disclosure_repo: DisclosureRequestRepository,
        molecule_repo: MoleculeRepository,
        merge_service: MergeService,
        structure_processor: StructureProcessorProtocol,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._disclosure_repo = disclosure_repo
        self._molecule_repo = molecule_repo
        self._merge_service = merge_service
        self._structure_processor = structure_processor
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: ResolveConflictCommand,
        auth: AuthContext | None = None,
    ) -> Result[DisclosureRequest, DomainError]:
        require_editor(auth)

        try:
            resolution = ConflictResolution(input.resolution)
        except ValueError:
            return Failure(
                ValidationError(
                    f"Invalid resolution '{input.resolution}'. "
                    f"Must be one of: {', '.join(ConflictResolution)}"
                )
            )

        async with self._uow:
            dr = await self._disclosure_repo.find_by_id(input.disclosure_id)
            if dr is None:
                return Failure(
                    NotFoundError("DisclosureRequest", str(input.disclosure_id))
                )

            # Workspace isolation via the molecule
            molecule = await self._molecule_repo.find_by_id(dr.molecule_id)
            if molecule is None or molecule.workspace_id != input.workspace_id:
                return Failure(
                    NotFoundError("DisclosureRequest", str(input.disclosure_id))
                )

            if dr.status != DisclosureStatus.CONFLICT:
                return Failure(
                    ValidationError(
                        f"Disclosure is in '{dr.status.value}' status, not 'conflict'"
                    )
                )

            if resolution == ConflictResolution.REJECT:
                return await self._handle_reject(dr, input)
            elif resolution == ConflictResolution.ACCEPT_AS_NEW:
                return await self._handle_accept_as_new(dr, molecule, input)
            else:
                return await self._handle_accept_merge(dr, molecule, input, auth)

    async def _handle_reject(
        self,
        dr: DisclosureRequest,
        input: ResolveConflictCommand,
    ) -> Result[DisclosureRequest, DomainError]:
        reason = input.reason or "Conflict rejected by admin"
        dr.reject(reason=reason)
        await self._disclosure_repo.save(dr)
        events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(dr)

    async def _handle_accept_as_new(
        self,
        dr: DisclosureRequest,
        molecule: object,
        input: ResolveConflictCommand,
    ) -> Result[DisclosureRequest, DomainError]:
        # Re-process the SMILES to get structure + descriptors
        process_result = self._structure_processor.process(dr.disclosed_smiles)
        if isinstance(process_result, Failure):
            return Failure(
                ValidationError(
                    f"Structure processing failed: {process_result.failure().message}"
                )
            )
        processed = process_result.unwrap()

        # Disclose the molecule in-place
        molecule.disclose(  # type: ignore[union-attr]
            structure=processed.structure,
            descriptors=processed.descriptors,
            disclosed_by=input.resolved_by,
        )

        dr.resolve_as_new_structure(
            canonical_smiles=processed.structure.smiles,
            inchi_key=processed.structure.inchi_key,
        )

        await self._molecule_repo.save(molecule)  # type: ignore[arg-type]
        await self._disclosure_repo.save(dr)
        events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(dr)

    async def _handle_accept_merge(
        self,
        dr: DisclosureRequest,
        molecule: object,
        input: ResolveConflictCommand,
        auth: AuthContext | None,
    ) -> Result[DisclosureRequest, DomainError]:
        # We need to find the target molecule by InChIKey
        if not dr.inchi_key:
            # Re-process to get InChIKey
            process_result = self._structure_processor.process(dr.disclosed_smiles)
            if isinstance(process_result, Failure):
                return Failure(
                    ValidationError(
                        f"Structure processing failed: {process_result.failure().message}"
                    )
                )
            processed = process_result.unwrap()
            canonical_smiles = processed.structure.smiles
            inchi_key = processed.structure.inchi_key
        else:
            canonical_smiles = dr.canonical_smiles or dr.disclosed_smiles
            inchi_key = dr.inchi_key

        target = await self._molecule_repo.find_by_inchi_key(
            input.workspace_id, inchi_key
        )
        if target is None:
            return Failure(
                ConflictError(
                    "No existing molecule with matching InChIKey found for merge"
                )
            )

        # Save DR before merge (in case merge transaction is separate)
        await self._disclosure_repo.save(dr)
        events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)

        # Delegate merge to MergeService (opens its own UoW)
        merge_result = await self._merge_service(
            MergeCommand(
                source_molecule_id=dr.molecule_id,
                target_molecule_id=target.id,
                reason=MergeReason.DISCLOSURE_RESOLVED,
                merged_by=input.resolved_by,
                disclosure_request_id=dr.id,
                notes=input.reason,
            ),
            auth=auth,
        )

        # Update DR based on merge outcome
        async with self._uow:
            loaded_dr = await self._disclosure_repo.find_by_id(dr.id)
            if loaded_dr is None:
                return Failure(
                    NotFoundError("DisclosureRequest", str(dr.id))
                )

            if isinstance(merge_result, Success):
                loaded_dr.resolve_as_merged(
                    canonical_smiles=canonical_smiles,
                    inchi_key=inchi_key,
                    resolved_to_molecule_id=target.id,
                )
            else:
                loaded_dr.reject(
                    reason=f"Merge failed: {merge_result.failure().message}"
                )

            await self._disclosure_repo.save(loaded_dr)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

            if isinstance(merge_result, Failure):
                return Failure(merge_result.failure())

            return Success(loaded_dr)
