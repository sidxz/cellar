"""RegisterMolecule command — register a new molecule (disclosed or undisclosed)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from returns.pipeline import is_successful
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.chemical_registration.protocols import (
    DetectedSaltDTO,
    StructureProcessorProtocol,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.workspace_config.custom_field_validator import CustomFieldValidator
from cellar.domain.chemical_registration.disclosure_request import DisclosureRequest
from cellar.domain.chemical_registration.enums import MoleculeType, RegistrationAction
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.chemical_registration.repository import (
    DisclosureRequestRepository,
    MoleculeRepository,
)
from cellar.domain.shared.errors import ConflictError, DomainError, ValidationError
from cellar.domain.workspace_config.enums import FieldTarget

if TYPE_CHECKING:
    from cellar.application.chemical_registration.disclosure_service import DisclosureService


@dataclass(frozen=True)
class RegistrationOutcome:
    """Result of a molecule registration."""

    molecule: Molecule
    is_new: bool
    action: RegistrationAction = RegistrationAction.REGISTERED
    qc_warnings: list[str] = field(default_factory=list)
    detected_salt: DetectedSaltDTO | None = None
    # Disclosure detection fields (populated by Task 3)
    needs_merge_confirmation: bool = False
    matched_molecule_id: uuid.UUID | None = None
    disclosure_id: uuid.UUID | None = None
    conflict_reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class ExternalId:
    identifier: str
    identifier_type: str


@dataclass(frozen=True, kw_only=True)
class RegisterMoleculeCommand(Command):
    workspace_id: uuid.UUID
    name: str
    smiles: str | None = None  # None for undisclosed
    molecule_type: str = MoleculeType.SMALL_MOLECULE.value
    external_ids: list[ExternalId] = field(default_factory=list)
    originating_org_id: uuid.UUID
    registered_by: uuid.UUID
    scientist_name: str | None = None
    custom_fields: dict[str, Any] | None = None
    qc_reject_threshold: int | None = None
    qc_warn_threshold: int | None = None
    promote_name_as_identifier: bool = True  # False for auto-generated names
    auto_approve: bool = True  # False from wizard — merge candidates need confirmation


class RegisterMolecule:
    """Use case: register a new molecule or add to existing one.

    For disclosed (smiles provided):
      standardize -> QC check -> InChIKey dedup -> ID dedup -> create or add batch

    For undisclosed (smiles is None):
      ID dedup only -> create

    Names are always auto-promoted to custom identifiers and subject to
    workspace-unique enforcement (per US-001 design guardrails).
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
        structure_processor: StructureProcessorProtocol,
        custom_field_validator: CustomFieldValidator | None = None,
        disclosure_repo: DisclosureRequestRepository | None = None,
        disclosure_service: DisclosureService | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._processor = structure_processor
        self._custom_field_validator = custom_field_validator
        self._disclosure_repo = disclosure_repo
        self._disclosure_service = disclosure_service

    async def __call__(
        self,
        input: RegisterMoleculeCommand,
        auth: AuthContext | None = None,
    ) -> Result[RegistrationOutcome, DomainError]:
        require_editor(auth)

        if input.smiles is not None:
            return await self._register_disclosed(input)
        return await self._register_undisclosed(input)

    def _collect_all_identifiers(self, input: RegisterMoleculeCommand) -> set[str]:
        """Collect name + all external IDs into a single set for batch lookup."""
        ids = {ext.identifier for ext in input.external_ids}
        if input.name and input.promote_name_as_identifier:
            ids.add(input.name)
        return ids

    async def _check_identifier_conflicts(
        self,
        input: RegisterMoleculeCommand,
        allowed_molecule_id: uuid.UUID | None,
    ) -> Result[None, DomainError]:
        """Batch-check all identifiers (name + external_ids) for conflicts.

        If allowed_molecule_id is set, identifiers already on that molecule
        are not considered conflicts (duplicate detection case).
        """
        all_ids = self._collect_all_identifiers(input)
        if not all_ids:
            return Success(None)

        existing_map = await self._repo.find_identifiers_in_workspace(input.workspace_id, all_ids)

        for identifier, owner_id in existing_map.items():
            if allowed_molecule_id is not None and owner_id == allowed_molecule_id:
                continue  # already on the target molecule — not a conflict
            return Failure(
                ConflictError(f"Identifier '{identifier}' is already assigned to another molecule")
            )

        return Success(None)

    def _add_name_and_ids(
        self,
        mol: Molecule,
        input: RegisterMoleculeCommand,
        source: str,
    ) -> None:
        """Add name as custom identifier + all external_ids to molecule."""
        existing_values = {i.identifier for i in mol.identifiers}

        # Auto-promote name as custom identifier (skip for auto-generated names)
        if input.name and input.promote_name_as_identifier and input.name not in existing_values:
            mol.add_identifier(
                MoleculeIdentifier.create(
                    molecule_id=mol.id,
                    identifier=input.name,
                    identifier_type="custom",
                    source=f"Registration ({source})",
                    registered_by=input.registered_by,
                )
            )
            existing_values.add(input.name)

        # Add explicit external IDs
        for ext_id in input.external_ids:
            if ext_id.identifier not in existing_values:
                mol.add_identifier(
                    MoleculeIdentifier.create(
                        molecule_id=mol.id,
                        identifier=ext_id.identifier,
                        identifier_type=ext_id.identifier_type,
                        source=f"Registration ({source})",
                        registered_by=input.registered_by,
                    )
                )
                existing_values.add(ext_id.identifier)

    async def _record_disclosure_provenance(
        self,
        input: RegisterMoleculeCommand,
        molecule_id: uuid.UUID,
        canonical_smiles: str,
        inchi_key: str,
        *,
        is_new: bool,
        resolved_to_molecule_id: uuid.UUID | None = None,
    ) -> None:
        """Create an auto-resolved DisclosureRequest for provenance tracking.

        Only records if a disclosure_repo was injected (opt-in).
        """
        if self._disclosure_repo is None:
            return

        dr = DisclosureRequest.create(
            workspace_id=input.workspace_id,
            molecule_id=molecule_id,
            disclosed_smiles=input.smiles,  # type: ignore[arg-type]
            requested_by=input.registered_by,
            disclosing_org_id=input.originating_org_id,
            scientist_name=input.scientist_name,
            notes="Auto-recorded during registration",
        )
        dr.start_processing()

        if is_new:
            dr.resolve_as_new_structure(
                canonical_smiles=canonical_smiles,
                inchi_key=inchi_key,
            )
        else:
            dr.resolve_as_merged(
                canonical_smiles=canonical_smiles,
                inchi_key=inchi_key,
                resolved_to_molecule_id=resolved_to_molecule_id,  # type: ignore[arg-type]
            )

        await self._disclosure_repo.save(dr)

    async def _register_disclosed(
        self, input: RegisterMoleculeCommand
    ) -> Result[RegistrationOutcome, DomainError]:
        # 1. Process structure (standardize + descriptors + fingerprints)
        proc_result = self._processor.process(
            input.smiles,  # type: ignore[arg-type]
            qc_reject_threshold=input.qc_reject_threshold,
        )
        if isinstance(proc_result, Failure):
            return Failure(proc_result.failure())

        processed = proc_result.unwrap()
        qc_warnings: list[str] = []
        if (
            input.qc_warn_threshold is not None
            and processed.qc_result.total_penalty >= input.qc_warn_threshold
        ):
            qc_warnings = processed.qc_result.issues

        inchi_key = processed.structure.inchi_key
        if inchi_key is None:
            return Failure(ValidationError("Structure processor returned no InChI key"))

        # Custom-field validation runs before opening the UoW since it has
        # its own session lifecycle and shouldn't share our transaction.
        if self._custom_field_validator and input.custom_fields:
            validation = await self._custom_field_validator.validate(
                input.custom_fields, FieldTarget.MOLECULE, input.workspace_id
            )
            if not is_successful(validation):
                return Failure(validation.failure())

        # Single UoW: read + branch + write happen in one transaction so
        # concurrent registrations of the same InChIKey can't both succeed
        # (the second one will hit a unique-constraint violation on commit
        # rather than silently double-registering).
        delegate_to_disclosure: Molecule | None = None
        outcome: RegistrationOutcome | None = None
        events: list = []

        async with self._uow:
            # 2. Check InChIKey against existing active molecules
            existing_by_inchi = await self._repo.find_by_inchi_key(input.workspace_id, inchi_key)

            # 3. Check for undisclosed molecule match (before conflict check)
            undisclosed_match: Molecule | None = None
            if existing_by_inchi is None and self._disclosure_service is not None:
                all_ids = self._collect_all_identifiers(input)
                if all_ids:
                    undisclosed_match = await self._repo.find_undisclosed_by_identifiers(
                        input.workspace_id, all_ids
                    )

            # 4. Batch-check all identifiers (name + external_ids) for conflicts.
            allowed_id = (
                existing_by_inchi.id
                if existing_by_inchi
                else (undisclosed_match.id if undisclosed_match else None)
            )
            conflict_check = await self._check_identifier_conflicts(
                input,
                allowed_molecule_id=allowed_id,
            )
            if isinstance(conflict_check, Failure):
                return Failure(conflict_check.failure())

            # 5. Branch on the outcome of the reads above.
            if undisclosed_match is not None and self._disclosure_service is not None:
                # Defer to disclosure_service — it manages its own UoW so we
                # exit ours first, no writes pending.
                delegate_to_disclosure = undisclosed_match
            elif existing_by_inchi is not None:
                # 6a. Duplicate InChIKey — add identifiers to existing molecule
                self._add_name_and_ids(existing_by_inchi, input, source="duplicate")
                await self._repo.save(existing_by_inchi)
                await self._record_disclosure_provenance(
                    input,
                    existing_by_inchi.id,
                    processed.structure.smiles,
                    inchi_key,
                    is_new=False,
                    resolved_to_molecule_id=existing_by_inchi.id,
                )
                events = await self._uow.commit()
                outcome = RegistrationOutcome(
                    molecule=existing_by_inchi,
                    is_new=False,
                    action=RegistrationAction.DEDUPLICATED,
                    qc_warnings=qc_warnings,
                    detected_salt=processed.detected_salt,
                )
            else:
                # 6b. New molecule — same transaction as the conflict check, so
                # the unique InChIKey + identifier constraints are enforced
                # against the same snapshot we read above.
                reg_number = await self._repo.next_registration_number(input.workspace_id)
                mol = Molecule.register_disclosed(
                    workspace_id=input.workspace_id,
                    registration_number=reg_number,
                    name=input.name,
                    molecule_type=MoleculeType(input.molecule_type),
                    structure=processed.structure,
                    descriptors=processed.descriptors,
                    originating_org_id=input.originating_org_id,
                    custom_fields=input.custom_fields,
                    stereochemistry=processed.stereochemistry,
                )
                mol.morgan_fp = processed.fingerprints.morgan
                mol.bemis_murcko_smiles = processed.bemis_murcko_smiles
                self._add_name_and_ids(mol, input, source="name")
                await self._repo.save(mol)
                await self._record_disclosure_provenance(
                    input,
                    mol.id,
                    processed.structure.smiles,
                    inchi_key,
                    is_new=True,
                )
                events = await self._uow.commit()
                outcome = RegistrationOutcome(
                    molecule=mol,
                    is_new=True,
                    action=RegistrationAction.REGISTERED,
                    qc_warnings=qc_warnings,
                    detected_salt=processed.detected_salt,
                )

        if delegate_to_disclosure is not None and self._disclosure_service is not None:
            from cellar.application.chemical_registration.disclosure_service import (
                SubmitDisclosureCommand,
            )

            disclosure_result = await self._disclosure_service(
                SubmitDisclosureCommand(
                    workspace_id=input.workspace_id,
                    molecule_id=delegate_to_disclosure.id,
                    disclosed_smiles=input.smiles,  # type: ignore[arg-type]
                    requested_by=input.registered_by,
                    disclosing_org_id=input.originating_org_id,
                    scientist_name=input.scientist_name,
                    auto_approve=input.auto_approve,
                    notes="Auto-detected via identifier match during registration",
                )
            )
            if isinstance(disclosure_result, Failure):
                return Failure(disclosure_result.failure())

            d_outcome = disclosure_result.unwrap()
            if d_outcome.needs_confirmation:
                action = RegistrationAction.MERGE_CANDIDATE
            elif d_outcome.was_merged:
                action = RegistrationAction.DEDUPLICATED
            else:
                action = RegistrationAction.DISCLOSED

            return Success(
                RegistrationOutcome(
                    molecule=delegate_to_disclosure,
                    is_new=False,
                    action=action,
                    qc_warnings=qc_warnings,
                    detected_salt=processed.detected_salt,
                    needs_merge_confirmation=d_outcome.needs_confirmation,
                    matched_molecule_id=d_outcome.matched_molecule_id,
                    disclosure_id=d_outcome.disclosure_request.id,
                )
            )

        await self._dispatcher.dispatch_all(events)
        assert outcome is not None  # one of the branches above sets it
        return Success(outcome)

    async def _register_undisclosed(
        self, input: RegisterMoleculeCommand
    ) -> Result[RegistrationOutcome, DomainError]:
        async with self._uow:
            # 1. Batch-check all identifiers (name + external_ids)
            all_ids = self._collect_all_identifiers(input)
            existing_map = await self._repo.find_identifiers_in_workspace(
                input.workspace_id, all_ids
            )

            # 2. Determine if any existing molecule is matched
            matched_molecule: Molecule | None = None
            matched_id: uuid.UUID | None = None

            for identifier, owner_id in existing_map.items():
                if matched_id is None:
                    matched_id = owner_id
                elif owner_id != matched_id:
                    return Failure(ConflictError("Identifiers map to different molecules"))

            if matched_id is not None:
                matched_molecule = await self._repo.find_by_id_in_workspace(
                    input.workspace_id, matched_id
                )
                if (
                    matched_molecule is not None
                    and matched_molecule.structure_status.value == "disclosed"
                ):
                    # One of our identifiers/name is claimed by a disclosed molecule
                    conflict_id = next(k for k, v in existing_map.items() if v == matched_id)
                    return Failure(
                        ConflictError(
                            f"Identifier '{conflict_id}' belongs to disclosed "
                            f"molecule '{matched_molecule.registration_number.value}'"
                        )
                    )

            # 3a. Matched existing undisclosed — add new IDs
            events = []
            if matched_molecule is not None:
                self._add_name_and_ids(matched_molecule, input, source="duplicate")
                await self._repo.save(matched_molecule)
                events = await self._uow.commit()

        if matched_molecule is not None:
            await self._dispatcher.dispatch_all(events)
            return Success(
                RegistrationOutcome(
                    molecule=matched_molecule, is_new=False, action=RegistrationAction.DEDUPLICATED
                )
            )

        # 4. New undisclosed molecule
        if self._custom_field_validator and input.custom_fields:
            validation = await self._custom_field_validator.validate(
                input.custom_fields, FieldTarget.MOLECULE, input.workspace_id
            )
            if not is_successful(validation):
                return Failure(validation.failure())

        async with self._uow:
            reg_number = await self._repo.next_registration_number(input.workspace_id)
            mol = Molecule.register_undisclosed(
                workspace_id=input.workspace_id,
                registration_number=reg_number,
                name=input.name,
                molecule_type=MoleculeType(input.molecule_type),
                originating_org_id=input.originating_org_id,
                custom_fields=input.custom_fields,
            )
            self._add_name_and_ids(mol, input, source="name")

            await self._repo.save(mol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(
            RegistrationOutcome(molecule=mol, is_new=True, action=RegistrationAction.REGISTERED)
        )
