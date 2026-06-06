"""ExportMoleculesSDF — generate SDF content for a list of molecule IDs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.chemical_registration.protocols import StructureProcessorProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.shared.errors import DomainError, ValidationError

MAX_SDF_EXPORT = 10_000


@dataclass(frozen=True, kw_only=True)
class ExportSDFQuery(Query):
    workspace_id: uuid.UUID
    molecule_ids: list[uuid.UUID]


class ExportMoleculesSDF:
    """Generate an SDF string for the requested molecules.

    Each molecule entry: MOL block (from SMILES via RDKit) + data fields + $$$$ delimiter.
    Molecules without SMILES (undisclosed) are skipped.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        processor: StructureProcessorProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._processor = processor

    async def __call__(
        self, input: ExportSDFQuery, *, auth: AuthContext | None = None
    ) -> Result[str, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        if len(input.molecule_ids) > MAX_SDF_EXPORT:
            return Failure(
                ValidationError(f"Cannot export more than {MAX_SDF_EXPORT} molecules at once.")
            )

        if not input.molecule_ids:
            return Success("")

        async with self._uow:
            molecules = await self._repo.find_by_ids(input.workspace_id, input.molecule_ids)
            parts: list[str] = []
            for mol in molecules:
                if not mol.structure or not mol.structure.smiles:
                    continue

                mol_block = self._processor.smiles_to_mol_block(mol.structure.smiles)
                if mol_block is None:
                    continue

                # Build SDF entry: molblock + data fields + $$$$
                entry = mol_block
                entry += _sdf_field("Name", mol.name)
                entry += _sdf_field("Registration_Number", mol.registration_number.value)
                if mol.descriptors:
                    if mol.descriptors.molecular_weight is not None:
                        entry += _sdf_field(
                            "Molecular_Weight", f"{mol.descriptors.molecular_weight:.2f}"
                        )
                    if mol.descriptors.logp is not None:
                        entry += _sdf_field("LogP", f"{mol.descriptors.logp:.2f}")
                    if mol.descriptors.molecular_formula:
                        entry += _sdf_field("Molecular_Formula", mol.descriptors.molecular_formula)
                if mol.structure.inchi_key:
                    entry += _sdf_field("InChIKey", mol.structure.inchi_key)
                entry += "$$$$\n"
                parts.append(entry)

            return Success("".join(parts))


def _sdf_field(name: str, value: str) -> str:
    """Format a single SDF data field."""
    return f"> <{name}>\n{value}\n\n"
