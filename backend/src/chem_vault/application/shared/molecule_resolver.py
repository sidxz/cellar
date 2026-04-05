"""MoleculeResolver — resolve heterogeneous molecule references to UUIDs.

Supports UUID, registration number, external ID, SMILES, InChI key, and name
lookups. Used by collection membership and any bulk operation that accepts
user-provided molecule references.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from chem_vault.application.chemical_registration.protocols import StructureProcessorProtocol
from chem_vault.domain.chemical_registration.repository import MoleculeRepository


class RefType(StrEnum):
    UUID = "uuid"
    REGISTRATION_NUMBER = "registration_number"
    EXTERNAL_ID = "external_id"
    SMILES = "smiles"
    INCHI_KEY = "inchi_key"
    NAME = "name"


@dataclass(frozen=True)
class MoleculeReference:
    value: str
    ref_type: RefType


@dataclass(frozen=True)
class ResolvedMolecule:
    ref: MoleculeReference
    molecule_id: uuid.UUID


@dataclass(frozen=True)
class UnresolvedMolecule:
    ref: MoleculeReference
    reason: str  # "not_found", "tombstone", "ambiguous", "invalid"


class MoleculeResolver:
    """Resolve a batch of heterogeneous molecule references to UUIDs."""

    def __init__(
        self,
        molecule_repo: MoleculeRepository,
        structure_processor: StructureProcessorProtocol,
    ) -> None:
        self._molecule_repo = molecule_repo
        self._structure_processor = structure_processor

    async def resolve(
        self,
        workspace_id: uuid.UUID,
        refs: list[MoleculeReference],
    ) -> tuple[list[ResolvedMolecule], list[UnresolvedMolecule]]:
        """Resolve each reference and return (resolved, unresolved) lists."""
        resolved: list[ResolvedMolecule] = []
        unresolved: list[UnresolvedMolecule] = []

        for ref in refs:
            result = await self._resolve_one(workspace_id, ref)
            if isinstance(result, ResolvedMolecule):
                resolved.append(result)
            else:
                unresolved.append(result)

        return resolved, unresolved

    async def _resolve_one(
        self, workspace_id: uuid.UUID, ref: MoleculeReference
    ) -> ResolvedMolecule | UnresolvedMolecule:
        """Dispatch to the appropriate resolver based on ref_type."""
        if ref.ref_type == RefType.UUID:
            return await self._resolve_uuid(workspace_id, ref)
        elif ref.ref_type == RefType.REGISTRATION_NUMBER:
            return await self._resolve_registration_number(workspace_id, ref)
        elif ref.ref_type == RefType.EXTERNAL_ID:
            return await self._resolve_external_id(workspace_id, ref)
        elif ref.ref_type == RefType.SMILES:
            return await self._resolve_smiles(workspace_id, ref)
        elif ref.ref_type == RefType.INCHI_KEY:
            return await self._resolve_inchi_key(workspace_id, ref)
        elif ref.ref_type == RefType.NAME:
            return await self._resolve_name(workspace_id, ref)
        else:
            return UnresolvedMolecule(ref=ref, reason="invalid")

    async def _resolve_uuid(
        self, workspace_id: uuid.UUID, ref: MoleculeReference
    ) -> ResolvedMolecule | UnresolvedMolecule:
        try:
            mol_id = uuid.UUID(ref.value)
        except ValueError:
            return UnresolvedMolecule(ref=ref, reason="invalid")

        mol = await self._molecule_repo.find_by_id(mol_id)
        if mol is None or mol.workspace_id != workspace_id:
            return UnresolvedMolecule(ref=ref, reason="not_found")
        if mol.is_tombstone:
            return UnresolvedMolecule(ref=ref, reason="tombstone")
        return ResolvedMolecule(ref=ref, molecule_id=mol.id)

    async def _resolve_registration_number(
        self, workspace_id: uuid.UUID, ref: MoleculeReference
    ) -> ResolvedMolecule | UnresolvedMolecule:
        mol = await self._molecule_repo.find_by_registration_number(
            workspace_id, ref.value
        )
        if mol is None:
            return UnresolvedMolecule(ref=ref, reason="not_found")
        if mol.is_tombstone:
            return UnresolvedMolecule(ref=ref, reason="tombstone")
        return ResolvedMolecule(ref=ref, molecule_id=mol.id)

    async def _resolve_external_id(
        self, workspace_id: uuid.UUID, ref: MoleculeReference
    ) -> ResolvedMolecule | UnresolvedMolecule:
        mol = await self._molecule_repo.find_by_identifier(workspace_id, ref.value)
        if mol is None:
            return UnresolvedMolecule(ref=ref, reason="not_found")
        if mol.is_tombstone:
            return UnresolvedMolecule(ref=ref, reason="tombstone")
        return ResolvedMolecule(ref=ref, molecule_id=mol.id)

    async def _resolve_smiles(
        self, workspace_id: uuid.UUID, ref: MoleculeReference
    ) -> ResolvedMolecule | UnresolvedMolecule:
        result = self._structure_processor.process(ref.value)
        if not result.is_success:
            return UnresolvedMolecule(ref=ref, reason="invalid")

        processed = result.unwrap()
        inchi_key = processed.structure.inchi_key
        if inchi_key is None:
            return UnresolvedMolecule(ref=ref, reason="invalid")

        mol = await self._molecule_repo.find_by_inchi_key(workspace_id, inchi_key)
        if mol is None:
            return UnresolvedMolecule(ref=ref, reason="not_found")
        if mol.is_tombstone:
            return UnresolvedMolecule(ref=ref, reason="tombstone")
        return ResolvedMolecule(ref=ref, molecule_id=mol.id)

    async def _resolve_inchi_key(
        self, workspace_id: uuid.UUID, ref: MoleculeReference
    ) -> ResolvedMolecule | UnresolvedMolecule:
        mol = await self._molecule_repo.find_by_inchi_key(workspace_id, ref.value)
        if mol is None:
            return UnresolvedMolecule(ref=ref, reason="not_found")
        if mol.is_tombstone:
            return UnresolvedMolecule(ref=ref, reason="tombstone")
        return ResolvedMolecule(ref=ref, molecule_id=mol.id)

    async def _resolve_name(
        self, workspace_id: uuid.UUID, ref: MoleculeReference
    ) -> ResolvedMolecule | UnresolvedMolecule:
        matches = await self._molecule_repo.find_active(
            workspace_id, search_term=ref.value, limit=2
        )
        if len(matches) == 0:
            return UnresolvedMolecule(ref=ref, reason="not_found")
        if len(matches) >= 2:
            return UnresolvedMolecule(ref=ref, reason="ambiguous")
        return ResolvedMolecule(ref=ref, molecule_id=matches[0].id)
