"""RegisterMolecule command — register a new molecule (disclosed or undisclosed)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.enums import (
    IdentifierType,
    MoleculeType,
    RegistrationStatus,
    SynthesisStatus,
)
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.application.chemical_registration.protocols import StructureProcessorProtocol
from chem_vault.domain.shared.errors import ConflictError, DomainError, ValidationError


@dataclass(frozen=True)
class RegistrationOutcome:
    """Result of a molecule registration."""

    molecule: Molecule
    is_new: bool
    qc_warnings: list[str] = field(default_factory=list)


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
    custom_fields: dict | None = None
    qc_reject_threshold: int | None = None
    qc_warn_threshold: int | None = None


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
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._processor = structure_processor

    async def __call__(
        self,
        input: RegisterMoleculeCommand,
        auth: AuthContext | None = None,
    ) -> Result[RegistrationOutcome, DomainError]:
        require_editor(auth)

        async with self._uow:
            if input.smiles is not None:
                return await self._register_disclosed(input)
            return await self._register_undisclosed(input)

    def _collect_all_identifiers(self, input: RegisterMoleculeCommand) -> set[str]:
        """Collect name + all external IDs into a single set for batch lookup."""
        ids = {ext.identifier for ext in input.external_ids}
        if input.name:
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

        existing_map = await self._repo.find_identifiers_in_workspace(
            input.workspace_id, all_ids
        )

        for identifier, owner_id in existing_map.items():
            if allowed_molecule_id is not None and owner_id == allowed_molecule_id:
                continue  # already on the target molecule — not a conflict
            return Failure(
                ConflictError(
                    f"Identifier '{identifier}' is already assigned to another molecule"
                )
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

        # Auto-promote name as custom identifier
        if input.name and input.name not in existing_values:
            mol.add_identifier(
                MoleculeIdentifier.create(
                    molecule_id=mol.id,
                    identifier=input.name,
                    identifier_type=IdentifierType.CUSTOM,
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
                        identifier_type=IdentifierType(ext_id.identifier_type),
                        source=f"Registration ({source})",
                        registered_by=input.registered_by,
                    )
                )
                existing_values.add(ext_id.identifier)

    async def _register_disclosed(
        self, input: RegisterMoleculeCommand
    ) -> Result[RegistrationOutcome, DomainError]:
        # 1. Process structure (standardize + descriptors + fingerprints)
        proc_result = self._processor.process(
            input.smiles,  # type: ignore[arg-type]
            qc_reject_threshold=input.qc_reject_threshold,
        )
        if isinstance(proc_result, Failure):
            return proc_result  # type: ignore[return-value]

        processed = proc_result.unwrap()
        qc_warnings: list[str] = []
        if input.qc_warn_threshold is not None and processed.qc_result.total_penalty >= input.qc_warn_threshold:
            qc_warnings = processed.qc_result.issues

        inchi_key = processed.structure.inchi_key
        assert inchi_key is not None

        # 2. Check InChIKey against existing active molecules
        existing_by_inchi = await self._repo.find_by_inchi_key(
            input.workspace_id, inchi_key
        )

        # 3. Batch-check all identifiers (name + external_ids) for conflicts
        conflict_check = await self._check_identifier_conflicts(
            input,
            allowed_molecule_id=existing_by_inchi.id if existing_by_inchi else None,
        )
        if isinstance(conflict_check, Failure):
            return conflict_check  # type: ignore[return-value]

        # 4a. Duplicate InChIKey — add identifiers to existing molecule
        if existing_by_inchi is not None:
            self._add_name_and_ids(existing_by_inchi, input, source="duplicate")
            await self._repo.save(existing_by_inchi)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(
                RegistrationOutcome(
                    molecule=existing_by_inchi, is_new=False, qc_warnings=qc_warnings
                )
            )

        # 4b. New molecule
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
        )
        self._add_name_and_ids(mol, input, source="name")

        await self._repo.save(mol)
        events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(
            RegistrationOutcome(molecule=mol, is_new=True, qc_warnings=qc_warnings)
        )

    async def _register_undisclosed(
        self, input: RegisterMoleculeCommand
    ) -> Result[RegistrationOutcome, DomainError]:
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
                return Failure(
                    ConflictError(
                        f"Identifiers map to different molecules"
                    )
                )

        if matched_id is not None:
            matched_molecule = await self._repo.find_by_id(matched_id)
            if matched_molecule is not None and matched_molecule.structure_status.value == "disclosed":
                # One of our identifiers/name is claimed by a disclosed molecule
                conflict_id = next(
                    k for k, v in existing_map.items() if v == matched_id
                )
                return Failure(
                    ConflictError(
                        f"Identifier '{conflict_id}' belongs to disclosed "
                        f"molecule '{matched_molecule.registration_number.value}'"
                    )
                )

        # 3a. Matched existing undisclosed — add new IDs
        if matched_molecule is not None:
            self._add_name_and_ids(matched_molecule, input, source="duplicate")
            await self._repo.save(matched_molecule)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(
                RegistrationOutcome(molecule=matched_molecule, is_new=False)
            )

        # 3b. Check for conflicts on identifiers not in existing_map
        #     (name might conflict with a different molecule's identifier)
        if existing_map:
            # All conflicts already handled above — only reached here if
            # all existing_map entries point to the same matched molecule.
            pass

        # 4. New undisclosed molecule
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
        return Success(RegistrationOutcome(molecule=mol, is_new=True))
