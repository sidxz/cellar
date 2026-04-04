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
    originating_org_id: uuid.UUID = field(default_factory=uuid.uuid4)
    custom_fields: dict | None = None
    registered_by: uuid.UUID = field(default_factory=uuid.uuid4)
    qc_reject_threshold: int | None = None
    qc_warn_threshold: int | None = None


class RegisterMolecule:
    """Use case: register a new molecule or add to existing one.

    For disclosed (smiles provided):
      standardize -> QC check -> InChIKey dedup -> ID dedup -> create or add batch

    For undisclosed (smiles is None):
      ID dedup only -> create
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

        # 3. Check external IDs
        for ext_id in input.external_ids:
            existing_by_id = await self._repo.find_by_identifier(
                input.workspace_id, ext_id.identifier
            )
            if existing_by_id is not None:
                if existing_by_inchi is None:
                    # InChIKey not found but ID exists on different molecule -> CONFLICT
                    return Failure(
                        ConflictError(
                            f"Identifier '{ext_id.identifier}' is already assigned "
                            f"to molecule '{existing_by_id.registration_number.value}'"
                        )
                    )
                if existing_by_id.id != existing_by_inchi.id:
                    # InChIKey matches mol A, ID matches mol B -> CONFLICT
                    return Failure(
                        ConflictError(
                            f"Identifier '{ext_id.identifier}' belongs to molecule "
                            f"'{existing_by_id.registration_number.value}' but InChIKey "
                            f"matches '{existing_by_inchi.registration_number.value}'"
                        )
                    )

        if existing_by_inchi is not None:
            # Existing molecule — add IDs, return as existing
            for ext_id in input.external_ids:
                has_id = any(
                    i.identifier == ext_id.identifier for i in existing_by_inchi.identifiers
                )
                if not has_id:
                    existing_by_inchi.add_identifier(
                        MoleculeIdentifier.create(
                            molecule_id=existing_by_inchi.id,
                            identifier=ext_id.identifier,
                            identifier_type=IdentifierType(ext_id.identifier_type),
                            source="Registration (duplicate)",
                            registered_by=input.registered_by,
                        )
                    )
            await self._repo.save(existing_by_inchi)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(
                RegistrationOutcome(
                    molecule=existing_by_inchi, is_new=False, qc_warnings=qc_warnings
                )
            )

        # New molecule
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

        for ext_id in input.external_ids:
            mol.add_identifier(
                MoleculeIdentifier.create(
                    molecule_id=mol.id,
                    identifier=ext_id.identifier,
                    identifier_type=IdentifierType(ext_id.identifier_type),
                    source="User registration",
                    registered_by=input.registered_by,
                )
            )

        await self._repo.save(mol)
        events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(
            RegistrationOutcome(molecule=mol, is_new=True, qc_warnings=qc_warnings)
        )

    async def _register_undisclosed(
        self, input: RegisterMoleculeCommand
    ) -> Result[RegistrationOutcome, DomainError]:
        # ID-only dedup check
        for ext_id in input.external_ids:
            existing = await self._repo.find_by_identifier(
                input.workspace_id, ext_id.identifier
            )
            if existing is not None:
                if existing.structure_status.value == "disclosed":
                    return Failure(
                        ConflictError(
                            f"Identifier '{ext_id.identifier}' belongs to disclosed "
                            f"molecule '{existing.registration_number.value}'"
                        )
                    )
                # Existing undisclosed — add IDs, return as existing
                for eid in input.external_ids:
                    has_id = any(
                        i.identifier == eid.identifier for i in existing.identifiers
                    )
                    if not has_id:
                        existing.add_identifier(
                            MoleculeIdentifier.create(
                                molecule_id=existing.id,
                                identifier=eid.identifier,
                                identifier_type=IdentifierType(eid.identifier_type),
                                source="Registration (duplicate)",
                                registered_by=input.registered_by,
                            )
                        )
                await self._repo.save(existing)
                events = await self._uow.commit()
                await self._dispatcher.dispatch_all(events)
                return Success(
                    RegistrationOutcome(molecule=existing, is_new=False)
                )

        # New undisclosed molecule
        reg_number = await self._repo.next_registration_number(input.workspace_id)
        mol = Molecule.register_undisclosed(
            workspace_id=input.workspace_id,
            registration_number=reg_number,
            name=input.name,
            molecule_type=MoleculeType(input.molecule_type),
            originating_org_id=input.originating_org_id,
            custom_fields=input.custom_fields,
        )

        for ext_id in input.external_ids:
            mol.add_identifier(
                MoleculeIdentifier.create(
                    molecule_id=mol.id,
                    identifier=ext_id.identifier,
                    identifier_type=IdentifierType(ext_id.identifier_type),
                    source="User registration",
                    registered_by=input.registered_by,
                )
            )

        await self._repo.save(mol)
        events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(RegistrationOutcome(molecule=mol, is_new=True))
