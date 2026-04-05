"""ExportMoleculesSDF — generate SDF content for a list of molecule IDs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import MolToMolBlock
from returns.result import Failure, Result, Success

from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.shared.errors import DomainError, ValidationError

MAX_SDF_EXPORT = 10_000


@dataclass(frozen=True, kw_only=True)
class ExportSDFCommand(Command):
    workspace_id: uuid.UUID
    molecule_ids: list[uuid.UUID]


class ExportMoleculesSDF:
    """Generate an SDF string for the requested molecules.

    Each molecule entry: MOL block (from SMILES via RDKit) + data fields + $$$$ delimiter.
    Molecules without SMILES (undisclosed) are skipped.
    """

    def __init__(self, uow: UnitOfWork, repo: MoleculeRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ExportSDFCommand, *, auth: object | None = None
    ) -> Result[str, DomainError]:
        if len(input.molecule_ids) > MAX_SDF_EXPORT:
            return Failure(
                ValidationError(
                    f"Cannot export more than {MAX_SDF_EXPORT} molecules at once."
                )
            )

        if not input.molecule_ids:
            return Success("")

        async with self._uow:
            parts: list[str] = []
            for mol_id in input.molecule_ids:
                mol = await self._repo.find_by_id(mol_id)
                if mol is None or mol.workspace_id != input.workspace_id:
                    continue
                if not mol.structure or not mol.structure.smiles:
                    continue

                rdmol = Chem.MolFromSmiles(mol.structure.smiles)
                if rdmol is None:
                    continue

                mol_block = MolToMolBlock(rdmol)

                # Build SDF entry: molblock + data fields + $$$$
                entry = mol_block
                entry += _sdf_field("Name", mol.name)
                entry += _sdf_field("Registration_Number", mol.registration_number.value)
                if mol.descriptors:
                    if mol.descriptors.molecular_weight is not None:
                        entry += _sdf_field("Molecular_Weight", f"{mol.descriptors.molecular_weight:.2f}")
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
